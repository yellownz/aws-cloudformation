class FilterModule(object): 
  ''' Returns dictionary of items with keyed overrides that override properties with a matching selector''' 
  def filters(self): 
    return { 
        'dict_override': dict_override, 
        'dict_to_kv_string': dict_to_kv_string 
    } 
 
def dict_override(source, overrides, selector='Type'): 
  return {pk:v for k,v in overrides.items() for pk, pv in source.items() if pv.get(selector) == k} 
 
# Returns dict as 'key1=value1<separator>key2=value2 ...' 
def dict_to_kv_string(source, separator=' '): 
  return ' '.join([ "{}='{}'".format(k,v) for k,v in source.items() ])