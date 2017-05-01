from jinja2 import Template,FileSystemLoader,Environment,TemplateNotFound
from ansible.plugins import filter_loader
from ansible.errors import AnsibleError
import yaml
import os

PROPERTY_TRANSFORM = 'Property::Transform'
RESOURCE_TRANSFORM = 'Resource::Transform'

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

def render_template(template_file, template_paths, filters={}, **kwargs):
  # Create Jinja environment
  environment = Environment()
  environment.loader = FileSystemLoader(template_paths)
  if filters:
    environment.filters = dict(environment.filters.items() + filters.items())
  # Render template
  try:
    template = environment.get_template(template_file)
    template_params = kwargs.get('params') or dict()
    rendered = template.render(template_params)
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

def resource_transform(data, filter_paths=[],template_paths=[]):
def stack_transform(data, filter_paths=[],template_paths=[]):
  filter_paths += [os.getcwd() + '/filter_plugins']
  template_paths += [os.getcwd() + '/templates']
  # Load Ansible filters  
  filters = ansible_filters(filter_paths)
  combine = filters['combine']
  # Get resource transforms - {Stack}.Resources.<Resource> where <Resource>.Type = Resource::Transform::<transform>
  transforms = [
    {
      'name': resource_key,
      'resource': resource_value,
      'output': render_template(os.path.basename(file), os.path.dirname(file),filters) 
    }
    for resource_key, resource_value in data['Resources'].iteritems() 
    if resource_value['Type'] == RESOURCE_TRANSFORM
    for file in [lookup_template(resource_value['Template'], template_paths)]
  ]
  # Merge transforms
  for transform in transforms:
    creation_policy = transform['resource'].get('CreationPolicy') or "Component"
    if creation_policy == "Child":
      # TODO - handle child stack creation logic
      continue
    else:
      transform_data = {'Resources': transform['output']['Resources'] }
    data = combine(data,transform_data,recursive=True)
    del data['Resources'][transform['name']]
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