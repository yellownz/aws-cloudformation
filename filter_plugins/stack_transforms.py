from jinja2 import Template,FileSystemLoader,Environment,TemplateNotFound
from ansible.plugins import filter_loader
from ansible.errors import AnsibleError
import yaml
import os
import re

PROPERTY_TRANSFORM = 'Property::Transform'
STACK_TRANSFORM = 'Stack::Transform'

class FilterModule(object):
  ''' Executes custom property transforms defined in a CloudFormation stack '''
  def filters(self):
    return {
        'property_transform': property_transform,
        'stack_transform': stack_transform
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
    if key == 'Ref' and item == search:
      if as_value:
        parent[parent_key] = replace
      else:
        node[key] = replace
    if key in ['Fn::FindInMap','Fn::GetAtt','Fn::If'] and item[0] == search:
      node[key][0] = replace
    if key == 'Condition' and search in item and parent_key != 'Properties':
      node[key] = replace
    if key == 'DependsOn' and search in item and parent_key != 'Properties':
      node[key][item.index(search)] = replace
    if key == 'Fn::Sub' and '${%s' % search in item:
      if as_value:
        replace_value = replace
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
        node[key] = item.replace('${%s' % search, '${%s' % replace)
  def walk(node, parent=[None], parent_key=0):
    if type(node) is list:
      for index, item in enumerate(node):
        walk(item, node, index)
    elif type(node) is dict:
      for key, item in node.items():
        parse(key, item, node, parent, parent_key)
        walk(item, node, key)
  walk(data)

def stack_transform(data, filter_paths=[],template_paths=[]):
  filter_paths += [os.getcwd() + '/filter_plugins']
  template_paths += [os.getcwd() + '/templates']
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
    if resource_value['Type'] == STACK_TRANSFORM
    for file in [lookup_template(resource_value['Template'], template_paths)]
  ]
  # Merge transforms
  for transform in transforms:
    name = transform['name']
    resource = transform['resource']
    resource_properties = resource['Properties']
    output = transform['output']
    output_parameters = output.get('Parameters')
    output_parameters = output.get('Parameters')
    creation_policy = resource.get('CreationPolicy') or "Component"
    if creation_policy == "Child":
      # TODO - handle child stack creation logic
      raise AnsibleError("Child stacks not currently supported")
    else:
      # Post processing of template
      # Rename keys in Resources, Mappings and Conditions
      for section in ['Resources','Mappings','Conditions','Outputs']:
        for key in output.get(section, {}).keys():
          output[section][name+key] = output[section].pop(key)
          search_and_replace(output, key, name+key)

      # Process parameters
      for output_param_key, output_param_value in output_parameters.iteritems():
        # Get corresponding transform property
        resource_property = resource_properties.get(output_param_key)
        if resource_property:
          search_and_replace(output, output_param_key, resource_property, as_value=True)
        else:
          if output_param_value.get('Default') is None:
            raise AnsibleError("Transform parameter %s is missing associated transform property and default value" % output_param_key)
          search_and_replace(output, output_param_key, output_param_value['Default'], as_value=True)
      # Rename main stack references to transform resource
      for key,value in output.get('Outputs', {}).iteritems():
        search_and_replace(data,'%s.%s' % (name, key.split(name)[-1]), value['Value'], as_value=True)
      transform_data = { 
        'Resources': output.get('Resources', {}),
        'Mappings': output.get('Mappings', {}),
        'Conditions': output.get('Conditions', {}),
        'Outputs': output.get('Outputs', {})
      }
    data = combine(data,transform_data,recursive=True)
    del data['Resources'][transform['name']]
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