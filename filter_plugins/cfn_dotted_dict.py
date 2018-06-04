import operator
import json
import re
from collections import defaultdict

class FilterModule(object):
  ''' Converts CloudFormation Template Parameters to Stack Input mappings '''
  def filters(self):
    return {
      'cfn_dotted_dict': cfn_dotted_dict
    }

def cfn_dotted_dict(vars, paths=[]):
  infinitedict = lambda: defaultdict(infinitedict)
  data = infinitedict()
  vars_keys = vars.keys()
  vars_keys.sort(key=len)
  params = [(k,vars[k]) for p in paths for k in vars_keys if k.startswith(p) ]
  for param in params:
    # Only process params with dotted syntax,others are processed by stack_overrides
    if re.search('[\[\]\*]+',param[0]):
      continue
    keys = param[0].split('.')
    parent = reduce(operator.getitem, keys[:-1], data)
    parent[keys[-1]] = param[1]
  return json.loads(json.dumps(data))
