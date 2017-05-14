class FilterModule(object):
  ''' Transforms security rule expressions to AWS security group syntax '''
  def filters(self):
    return {
        'security_rules': security_rules
    }

def parse(port_expr):
    if str(port_expr).lstrip('-').isdigit():
      protocol = 'tcp'
      from_port = port_expr
      to_port = port_expr
    else:
      parts = port_expr.split('/')
      protocol = parts[0]
      from_port = parts[-1].split('-')[0]
      to_port = parts[-1].split('-')[-1]
      if protocol == from_port:
        protocol = 'tcp'
    return (protocol,from_port,to_port)

def security_rules(rules):  
  return [
    {
      'IpProtocol':parse(port_expr)[0],
      'FromPort': parse(port_expr)[1], 
      'ToPort': parse(port_expr)[2], 
      'CidrIp': cidr_ip
    } 
    for rule in rules for cidr_ip in rule['CidrIp'] for port_expr in rule['Ports']
  ]