import re

class FilterModule(object):
  ''' Converts CloudFormation Template Parameters to Stack Input mappings '''
  def filters(self):
    return {
        'stack_inputs': stack_inputs
    }

def camel_case(text):
  str1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
  return re.sub('([a-z0-9])([A-Z])', r'\1_\2', str1).lower()

def stack_inputs(inputs, vars={}, prefix='config_'):
  result = {}
  for key,value in inputs.items():
    try:
      camel = prefix + camel_case(key)
      result[key] = vars.get(camel) or value['Default']
    except KeyError as e:
      raise KeyError("Missing %s variable for %s input.  Please define this variable or specify a 'Default' property for the input." % (camel,key))
  return result
