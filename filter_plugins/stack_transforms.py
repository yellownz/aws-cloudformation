from jinja2 import Template,FileSystemLoader,Environment,TemplateNotFound
from ansible.plugins.loader import filter_loader
from ansible.errors import AnsibleError
import yaml
import os
import re
import logging

FORMAT = "[stack_transform]: %(message)s"
PROPERTY_TRANSFORM = 'Property::Transform'
STACK_TRANSFORM = 'Stack::Transform'
CHILD_STACK = 'AWS::CloudFormation::Stack'

class FilterModule(object):
  ''' Executes custom property transforms defined in a CloudFormation stack '''
  def filters(self):
    return {
        'property_transform': property_transform,
        'stack_transform': stack_transform,
        'stack_output': stack_output
    }

def stack_output(data):
  return { 
    k: data[k] 
    for k in [
      'AWSTemplateFormatVersion',
      'Description',
      'Metadata',
      'Parameters',
      'Mappings',
      'Conditions',
      'Transform',
      'Resources',
      'Outputs'
    ]
    if k in data.keys()
  }

def lookup_template(file, template_paths=os.getcwd()):
  template_file = next((
    os.path.abspath(path)
    for template_path in template_paths
    for path in [os.path.join(template_path, file)]
    if os.path.exists(path)
  ), None)
  if not template_file:
    raise AnsibleError("Could not locate template %s in paths %s" % (file,template_paths))
  return template_file

def render_template(template_file, template_paths, data, filters={}, **kwargs):
  # Create Jinja environment
  environment = Environment()
  environment.loader = FileSystemLoader(template_paths)
  if filters:
    environment.filters = dict(environment.filters.items() + filters.items())
  # Render template, passing data in as Config dictionary
  try:
    template = environment.get_template(template_file)
    rendered = template.render({'Config': data})
    return yaml.load(rendered)
  except TemplateNotFound as e:
    raise AnsibleError("Could not locate template %s in the supplied template paths %s" % (template_file,template_paths))
  except Exception as e:
    raise AnsibleError("An error occurred: %s" % e)

def ansible_filters(filter_paths):
  # Load Ansible filters  
  for path in filter_paths:
    filter_loader.add_directory(path)
  return { k:v for filter in filter_loader.all() for k,v in filter.filters().items() }

# Joins a list of items with a delimiter object
# e.g. [{'Ref':'AWS::StackName'},'-Thing'] => [{'Ref':'AWS::StackName'},{'Fn::ImportValue':'xyz'},'-Thing']
def list_join(items, delimiter):
  return reduce(lambda acc,item: acc + [delimiter] + [item] if acc else acc + [item], items, [])

# Splits an Fn::Sub expression and returns list with parameter expressions replaced with Refs
# e.g. '${AWS::StackName}-Thing' => [{'Ref':'AWS::StackName'},'-Thing']
def ref_replace(s, regex='\${([^{}]*)}'):
  parts = re.split(regex,s)
  return [ {'Ref': parts[n] } if n % 2 else parts[n] for n in range(len(parts)) if parts[n] ]

# Walks stack data structure and searchs and replaces a given parameter
def search_and_replace(data, search, replace, as_value=False):
  # Fn::Sub is evil!
  def parse_fn_sub_instrinsic_functions(item, node, parent, parent_key):
    ascii_node = {str(k): str(v) for k, v in node.items()}
    parts = ascii_node['Fn::Sub'].split('${%s}' % search)
    joined_parts = list_join(parts, replace)
    ref_replaced = reduce(
      lambda acc,item: acc + ref_replace(item) 
      if type(item) is str else acc + [item], joined_parts, [])
    parent[parent_key] = { 'Fn::Join': ['', ref_replaced ] }
  def parse(key, item, node, parent, parent_key):
    if node == search:
      parent[parent_key] = replace
    elif key == 'Ref' and item == search:
      if as_value:
        parent[parent_key] = replace
      else:
        node[key] = replace
    elif key in ['Fn::FindInMap','Fn::GetAtt','Fn::If'] and item[0] == search:
      node[key][0] = replace
    elif key == 'Condition' and search == item and parent_key != 'Properties' and isinstance(replace, (basestring,int)):
      node[key] = replace
    elif key == 'DependsOn' and search in item and parent_key != 'Properties' and isinstance(replace, (basestring,int)):
      node[key][item.index(search)] = replace
    elif key == 'DependsOn' and search in item and parent_key != 'Properties' and isinstance(replace, list):
      del node[key][item.index(search)]
      node[key] += replace
    elif key == 'Fn::Sub' and '${%s' % search in item:
      replace_value = str(replace)
      if as_value:
        if type(replace) is dict and 'Ref' in replace.keys():
          replace_value = '${%s}' % replace['Ref']
          node[key] = item.replace('${%s}' % search, replace_value)
        elif type(replace) is dict and 'Fn::Sub' in replace.keys():
          replace_value = replace['Fn::Sub']
          node[key] = item.replace('${%s}' % search, replace_value)
        elif type(replace) is dict and 'Fn::GetAtt' in replace.keys():
          replace_value = '${%s}' % ('.').join(replace['Fn::GetAtt'])
          node[key] = item.replace('${%s}' % search, replace_value)
        elif type(replace) is dict and 'Fn::GetAtt' in replace.keys():
          replace_value = '${%s}' % ('.').join(replace['Fn::GetAtt'])
          node[key] = item.replace('${%s}' % search, replace_value)
        elif type(replace) is dict and list(set(['Fn::ImportValue','Fn::If','Fn::Join','Fn::Select']) & set(replace.keys())):
          parse_fn_sub_instrinsic_functions(item, node, parent, parent_key)
        else:
          node[key] = item.replace('${%s}' % search, replace_value)
      else:
        node[key] = item.replace('${%s' % search, '${%s' % replace_value)
  def walk(node, parent=[None], parent_key=0):
    if type(node) is list:
      for index, item in enumerate(node):
        walk(item, node, index)
    elif type(node) is dict:
      for key, item in node.items():
        parse(key, item, node, parent, parent_key)
        walk(item, node, key)
  walk(data)

def find_in_sub(search, values):
  if search:
    return [v for v in values if search.find('${%s' % v) >= 0]
  else:
    return []

def fix_conditions(data, transform, input_parameter_key, input_parameter_value, resource_property):
  resource_keys = data['Resources'].keys()
  if (isinstance(resource_property, dict) and
      (resource_property.get('Ref') in resource_keys or
       resource_property.get('Fn::GetAtt') or 
       resource_property.get('Fn::ImportValue') or
       find_in_sub(resource_property.get('Fn::Sub'),resource_keys))):
    # Find and replace any conditions that reference an illegal input parameter
    for c,v in transform.get('Conditions',{}).iteritems():
      logging.debug("--> Forcing evaluation of condition %s as it references an illegal input value", c)
      search_and_replace(transform['Conditions'],{'Ref':input_parameter_key}, input_parameter_key)

def stack_transform(data, filter_paths=[],template_paths=[], debug=False):
  # Set logging level
  if debug:
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)

  # Prefer local playbook paths for filter and template lookups
  filter_paths = [os.getcwd() + '/filter_plugins'] + filter_paths
  template_paths = [os.getcwd() + '/templates'] + template_paths
  
  # Load Ansible filters  
  filters = ansible_filters(filter_paths)
  combine = filters['combine']

  # Get resource transforms - {Stack}.Resources.<Resource> where <Resource>.Type = Stack::Transform::<transform>
  transforms = [
    {
      'name': resource_key,
      'resource': resource_value,
      'output': render_template(os.path.basename(file), os.path.dirname(file), resource_value, filters) 
    }
    for resource_key, resource_value in data['Resources'].iteritems() 
    if resource_value.get('Type') == CHILD_STACK 
    and resource_value.get('Metadata',{}).get(STACK_TRANSFORM,{}).get('Strategy','merge').lower() == 'merge'
    for file in [lookup_template(resource_value['Metadata'][STACK_TRANSFORM]['Template'], template_paths)]
  ]

  # Scan input parameters for each transform, calculate renamed parameter,
  # and rename any references to transform outputs in main stack.
  logging.debug("STAGE 1: RENAME MAIN STACK REFERENCES TO TRANSFORM OUTPUTS")
  for transform in transforms:
    name = transform['name']
    transform_parameters = transform['output'].get('Parameters', {})
    logging.debug("%s: Renaming input references in main stack", name)
    for key in transform['output'].get('Outputs', {}).keys():
      logging.debug("--> Renaming %s.Outputs.%s to %s", name, key, name+key)
      search_and_replace(data,'%s.Outputs.%s' % (name, key), name+key)
      logging.debug("--> Replacing {'Fn::GetAtt': ['%s','Outputs.%s']} with %s", name, key, {'Ref': name+key})
      search_and_replace(data, {'Fn::GetAtt': [name,'Outputs.'+key]}, {'Ref': name+key})

  # Process each transform template, renaming template resources,
  # and merging template resources into main stack.
  logging.debug("STAGE 2: PROCESS TRANSFORM AND MERGE INTO MAIN STACK")
  for transform in transforms:
    name = transform['name']
    resource = transform['resource']
    resource_properties = resource['Properties']['Parameters']
    output = transform['output']
    output_parameters = output.get('Parameters', {})

    # Rename keys in Resources, Mappings, Conditions and Outputs
    logging.debug("%s: Renaming transform references", name)
    for section in ['Resources','Mappings','Conditions','Outputs']:
      for key in output.get(section, {}).keys():
        # Check if renamed resources will clash with main stack
        if section != 'Outputs' and name+key in data.get(section, {}).keys():
          raise AnsibleError("ERROR: The key %s in transform %s clashes with object %s in main stack '%s'" % (key, name, name+key, section))
        output[section][name+key] = output[section].pop(key)
        logging.debug("--> Renaming %s to %s", key, name+key)
        search_and_replace(output, key, name+key)

    # Fix conditions that will result in illegally referencing a resource
    logging.debug("%s: Evaluating conditions that reference a resource or stack export", name)
    for output_param_key, output_param_value in output_parameters.iteritems():
      resource_property = resource_properties.get(output_param_key)
      if resource_property:
        fix_conditions(data, output, output_param_key, output_param_value, resource_property)

    # Process input parameters
    logging.debug("%s: Replacing transform input parameter values", name)
    for output_param_key, output_param_value in output_parameters.iteritems():
      # Get corresponding transform input property from main stack
      resource_property = resource_properties.get(output_param_key)
      if resource_property:
        # Replace input parameter values with the transform input property value
        logging.debug("--> Replacing %s value with %s", output_param_key, resource_property)
        search_and_replace(output, output_param_key, resource_property, as_value=True)
      else:
        # Replace input parameter values with input parameter default or raise error
        default_value = output_param_value.get('Default')
        if default_value is None:
          raise AnsibleError("Transform parameter %s is missing associated transform property and default value" % output_param_key)
        logging.debug("--> Replacing %s value with %s", output_param_key, default_value)
        search_and_replace(output, output_param_key, default_value, as_value=True)
  
  # Replace references to merged transform outputs with transformed output values
  logging.debug("STAGE 3: REPLACE TRANSFORMED OUTPUT VALUES IN MAIN STACK")
  for transform in transforms:
    name = transform['name']
    output = transform['output']
    dependency_mapping = output.get('Metadata',{}).get(STACK_TRANSFORM,{}).get('DefaultDependencyMappings',[])
    dependencies = transform['resource'].get('DependsOn')
    for mapping in dependency_mapping:
      if dependencies:
        logging.debug("%s: Attaching 'DependsOn: %s' to default resource %s", name, dependencies, name+mapping)
        if output['Resources'][name+mapping].get('DependsOn'):
          output['Resources'][name+mapping]['DependsOn'] += dependencies
        else:
          output['Resources'][name+mapping]['DependsOn'] = dependencies
    logging.debug("%s: Replacing transformed output values in main stack", name)
    for key,value in output.get('Outputs', {}).iteritems():
      replaced_value = value['Value']
      logging.debug("--> Replacing %s value with %s", key, replaced_value)
      search_and_replace(data, key, replaced_value, as_value=True)
    transform_data = { 
      'Resources': output.get('Resources', {}),
      'Mappings': output.get('Mappings', {}),
      'Conditions': output.get('Conditions', {})
    }
    data = combine(data,transform_data,recursive=True)
    del data['Resources'][transform['name']]
    # Finally replace any DependsOn references to transform with the default dependency mapping
    if dependency_mapping:
      renamed_dependency_mapping = [name+mapping for mapping in dependency_mapping]
      logging.debug("%s: Replacing '%s' dependencies with default mapping %s", name, name, renamed_dependency_mapping)
      search_and_replace(data, name, renamed_dependency_mapping, as_value=True)
  return data

def property_transform(data, filter_paths=[]):
  # Load Ansible filters
  filter_paths += [os.getcwd() + '/filter_plugins']
  filters = ansible_filters(filter_paths)
  # Get transform properties - {Stack}.Resources.<Resource>.Properties.<Property>.Property::Transform
  transforms = [ 
    {'resource':resource_key, 'property': property_key}
    for resource_key, resource_value in data['Resources'].iteritems() 
      if resource_value.get('Properties')
    for property_key, property_value in resource_value.get('Properties').iteritems() 
      if type(property_value) is dict and property_value.get(PROPERTY_TRANSFORM)
  ]
  for transform in transforms:
    property = transform['property']
    resource = transform['resource']
    # Parse transform configuration
    filter_name = data['Resources'][resource]['Properties'][property][PROPERTY_TRANSFORM][0]
    filter_data = data['Resources'][resource]['Properties'][property][PROPERTY_TRANSFORM][1]
    # Transform data
    data['Resources'][resource]['Properties'][property] = filters[filter_name](filter_data)
  return data