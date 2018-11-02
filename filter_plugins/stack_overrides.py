import re
import jmespath

class FilterModule(object):
  ''' Converts CloudFormation Template Parameters to Stack Input mappings '''
  def filters(self):
    return {
      'stack_overrides': stack_overrides
    }

# Flattens list of lists until the inner most list is reached
# Then mutates element inner most list at index with data
def flatten(op, parent, data, index=0):
  for p in parent:
    if type(p) is list:
      flatten(op, p, data, index)
    else:
      op(parent, data, index)
      break

# Assign operator for flatten
def assign(parent, data, index):
  parent[index] = data

# Append operator for flatten
def append(parent, data, index):
  parent += data

def stack_overrides(vars, source='Stack', paths=[
  'Description','Metadata','Parameters', 'Resources', 'Mappings', 'Outputs', 'Conditions'
]):
  # Selects top level source object - e.g. 'Stack'
  data = vars[source]
  # Sort keys based upon selector depth
  vars_keys = list(vars.keys())
  vars_keys.sort(key=lambda k: len(k.split(".")))  # TODO: what if filters have '.' characters?
  # Assuming [{'Stack.x.x.x': 'value'}...]
  # Returns tuples in form [('Stack.x.x.x', 'value')...]
  params = [(k,vars[k]) for p in paths for k in vars_keys if k.startswith(source + '.' + p)]
  for param in params:
    # Ignore params with only dotted syntax, they are processed by dotted dict
    if not re.search('[\[\]\*]+',param[0]):
      continue
    parts = param[0].split(".",1)
    if len(parts) == 1:
      data = param[1]
      continue
    parts = parts[1].rsplit(".",1)
    if len(parts) == 1:
      data[parts[0]] = param[1]
      continue
    path = parts[0]
    key = parts[1]
    key_parts = re.match('(.*)\[(.*)\]$',key)
    if key_parts:
      key_prop = key_parts.groups()[0]
      key_filter = key_parts.groups()[1]
      if key_filter and key_filter.isdigit():
        # Example: Stack.Resources.MyResource.Values[0]: <new value>
        # Here we need to select path + key_prop and then use key_filter as index
        parent = jmespath.search(path + '.' + key_prop, data)
        if parent is None:
          continue
        if type(parent) is list:
          flatten(assign, parent, param[1], int(key_filter))
        else:
          parent[int(key_filter)] = param[1]
      elif not key_filter:
        # Example: Stack.Resources.MyResource.Values[]: <new value>
        # Here we need to add value to path + key_prop
        parent = jmespath.search(path + '.' + key_prop, data)
        if parent is None:
          continue
        flatten(append, parent, param[1])
      else:
        # Example: Stack.Resources.MyResource.Values[?prop='value']: <new value>
        # Here we assume <new value> is a dict and we need to replace dict keys/values with <new value? keys/values
        parent = jmespath.search(path + '.' + key, data)
        if parent is None:
          continue
        for p in parent:
          for k in list(p):
            del p[k]
          for k,v in param[1].items():
            p[k] = v
    else:
      parent = jmespath.search(path, data)
      if parent is None:
        continue
      if type(parent) is list:
        for p in parent:
          p[key] = param[1]
      else:
        parent[key] = param[1]  
  return data
