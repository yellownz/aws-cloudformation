from time import time

class FilterModule(object):
  ''' Returns dictionary of items with keyed overrides that override properties with a matching selector'''
  def filters(self):
    return {
        'timestamp': timestamp
    }

def timestamp(source=None):
  return int(time())
