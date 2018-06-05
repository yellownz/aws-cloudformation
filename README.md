# AWS CloudFormation Role

This is an Ansible role for generating CloudFormation templates and deploying CloudFormation stacks to Amazon Web Services.

## Requirements

- Python 2.7
- PIP package manager (**easy_install pip**)
- Ansible 2.4 or greater (**pip install ansible**)
- Boto3 (**pip install boto3**)
- Netaddr (**pip install netaddr**)
- AWS CLI (**pip install awscli**) installed and configured

## Setup

The recommended approach to use this role is an Ansible Galaxy requirement to your Ansible playbook project.

Alternatively you can also configure this repository as a Git submodule to your Ansible playbook project.

The role should be placed in the folder **roles/aws-cloudformation**, and can then be referenced from your playbooks as a role called `aws-cloudformation`.

You should also specify a specific release that is compatible with your playbook.

### Install using Ansible Galaxy

To set this role up as an Ansible Galaxy requirement, first create a `requirements.yml` file in a `roles` subfolder of your playbook and add an entry for this role.  See the [Ansible Galaxy documentation](http://docs.ansible.com/ansible/galaxy.html#installing-multiple-roles-from-a-file) for more details.

```
# Example requirements.yml file
- src: git@github.com:Casecommons/aws-cloudformation.git
  scm: git
  version: 0.1.0
  name: aws-cloudformation
```

Once you have created `requirements.yml`, you can install the role using the `ansible-galaxy` command line tool.

```
$ ansible-galaxy install -r roles/requirements.yml -p ./roles/ --force
```

To update the role version, simply update the `requirements.yml` file and re-install the role as demonstrated above.

### Installing using Git Submodule

You can also install this role by adding this repository as a Git submodule and then checking out the required version:

```
$ git submodule add git@github.com:Casecommons/aws-cloudformation.git roles/aws-cloudformation
Submodule path 'roles/aws-cloudformation': checked out '05f584e53b0084f1a2a6a24de6380233768a1cf0'
$ cd roles/aws-cloudformation
roles/aws-cloudformation$ git checkout 0.1.0
roles/aws-cloudformation$ cd ../..
$ git commit -a -m "Added aws-cloudformation 0.1.0 role"
```

If you add this role as a submodule, you can update to later versions of this role by updating your submodules:

```
$ git submodule update --remote roles/aws-cloudformation
$ cd roles/aws-cloudformation
roles/aws-cloudformation$ git checkout 0.2.0
roles/aws-cloudformation$ cd ../..
$ git commit -a -m "Updated to aws-cloudformation 0.2.0 role"
```

## Usage

This role is designed to be used with Yellow NZ CloudFormation stacks and relies on a CloudFormation template file being provided by the consuming playbook.

The default convention is to create the template file at the path `templates/stack.yml.j2` in the playbook repository.

> You can override the default template file by setting the `Stack.Template` variable.

The format of the CloudFormation template is a [Jinja2 template](http://jinja.pocoo.org/docs/dev/), although you can provide a literal template.  This allows you to perform Jinja2 template variable substitution and more advanced constructs to generate your CloudFormation templates if appropriate.

The following variables are used to configure this role:

- `Stack.Name` (required) - defines the stack name
- `Stack.Description` (optional) - defines the stack description.  This will override the template stack description.
- `Stack.Inputs` (optional) - a dictionary of stack inputs to provide to the stack.  See the [Stack Inputs](#stack-inputs) section for further details.
- `Stack.Policy` (optional) - defines the stack policy in a YAML or JSON format.
- `Stack.Bucket` (optional) - defines the S3 bucket where the CloudFormation template will be uploaded.  This defaults to `<account-id>-cfn-templates` if not specified.
- `Stack.Upload` (optional) - uploads the generated CloudFormation template to an S3 bucket defined by the `Stack.Bucket` variable.  Defaults to `false`.
- `Stack.Role` (optional) - specifies a [CloudFormation service role](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html)

Invoking this role will generate a folder called `build` in the current working directory, along with a timestamped folder of the current date (e.g. `./build/20160705154440/`).  Inside this folder the following files are created:

- `<stack-name>-stack.yml` - the generated CloudFormation template in human readable YAML format.
- `<stack-name>-stack.json` - the generated CloudFormation template in compact JSON format.  This is the template that is uploaded to the AWS CloudFormation service when creating or updating a stack.
- `<stack-name>-policy.json` - the stack policy JSON file that is uploaded to the AWS CloudFormation service.
- `<stack-name>-config.json` - configuration file that defines stack policy, stack tags and stack inputs in a JSON format.  This file is used by AWS CodePipeline CloudFormation deployment actions.

### Stack Inputs

Stack inputs are configured via the `Stack.Inputs` dictionary based upon the following conventions:

- Each stack template parameter is defined in a variable named `Stack.Inputs.<Parameter-Name>`.  E.g. if the template parameter is `ApplicationInstanceType` - you need to have `Stack.Inputs.ApplicationInstanceType` defined in your environment settings.
- If `Stack.Inputs.<Parameter-Name>` is not defined but the parameter has a `Default` property, then the `Default` property value will be used
- If `Stack.Inputs.<Parameter-Name>` is not defined and the parameter does not have a `Default` property, a KeyError will be thrown with a message `Missing variable for ApplicationKeyName input.  Please define this variable or specify a 'Default' property for the input`

### Stack Overrides

You can override any portion of a CloudFormation template using JMESPath query notation:

```
# Overrides the MyProperty property with the Properties dictionary for the MyResource resource
# This is a simple override in that it only traverses a dictionary path to reach the leaf element
Stack.Resources.MyResource.Properties.MyProperty: foo

# The remaining examples are complex overrides, in that they contain list elements and therefore the leaf element may refer to multiple elements
# This will replace the Environment property in the first container definition of the MyResource resource
Stack.Resources.MyResource.Properties.ContainerDefinitions[0].Environment:
  - Name: FOO
    Value: bar

# This will append (rather than replace) the specified value(s) to the Environment property in the first container definition
Stack.Resources.MyResource.Properties.ContainerDefinitions[0].Environment[]:
  - Name: FOO
    Value: bar

# This will replace all Environment property for all ContainerDefinitions with a Name of squid
Stack.Resources.MyResource.Properties.ContainerDefinitions[?Name=='squid'].Environment:
  - Name: FOO
    Value: bar
```

Note the following behaviors:

- For complex overrides (see example above), the override will not be applied if elements returned by the query do not exist
- For simple overrides (see example above), the override will be added to the dictionary tree if the element returned by the query does not exist.  This is useful for adding additional resources or other elements to your stack.
- Complex overrides take precedence over simple overrides

For example, if your template doesn't include any mappings, the following simple override will add the specified mapping, even though the mapping does not exist:

```
# If the Accounts mapping already exists in the template it will be overriden
# If the Accounts mapping does not exist it will be created
Stack.Mappings.Accounts:
  dev:
    id: 12345
    users:
      - justin
  staging:
    id: 54321
    users:
      - pema
```

However contrast the behavior when using a complex override:

```
# If the Accounts mapping already exists in the template, the id property on any child elements of the Accounts mapping will be overridden
# If the Accounts mapping does not exist or the id property is not defined, no changes will be made
Stack.Mappings.Accounts.*.id: 55555
```

### S3 Template Upload

The S3 template upload feature is enabled by default, but can be disabled if required by setting the variable `Stack.Upload` to `false`.

The `<stack-name>-stack.json` template will be uploaded to an S3 bucket as defined by the variable `Stack.Bucket`.

### Generating a Template Only

You can generate a template only by passing the tag `generate` to this role.  This will only create the templates as described above, but not attempt to create or update the stack in CloudFormation.

`ansible-playbook site.yml -e env=dev --tags generate`

Note the generated template will be uploaded to S3 as described earlier.

### Temporarily Disabling Stack Policy

You can temporarily disable the stack policy for a provisioning run by setting the variable `Stack.DisablePolicy` to true:

`ansible-playbook site.yml -e env=prod -e Stack.DisablePolicy=true`

This will set to the stack policy to the following policy before stack modification:

```
{
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "Update:*",
        "Principal": "*",
        "Resource" : "*"
      }
    ]
  }
```

And then after stack modification is complete, reset the stack policy to it's previous state.

> Note: This role will also reset the stack policy in the event of a stack modification failure

### Disabling Stack Rollback

You can disable stack rollback by setting the `Stack.DisableRollback` variable to true:

`ansible-playbook site.yml -e env=prod -e Stack.DisableRollback=true`

### Role Facts

This role sets the following facts that you can use subsequently in your roles:

- `cloudformation['<stack-name>']` - CloudFormation facts about the created stack.  This includes stack resources and stack outputs.
- `Stack.Facts` - CloudFormation facts about the created stack.  This includes stack resources and stack outputs and is identical to the `cloudformation['<stack-name>']` fact.
- `Stack.Url` - S3 URL of the CloudFormation template.  This is also printed at the end of the completion of this role.

## Macros

This role includes Jinja macros which can automatically generate CloudFormation resources using common conventions and patterns.

Macros are located in the [`macros`](./macros) folder and create resources and outputs for various resource types.

Macros are structured according to the following conventions:

- Separate files exist for each resource category or type.  For example, the `network.j2` macros create all networking related resources and outputs according to a set of standard conventions.

- Each macro file defines a resources macro, which will create resources based upon a set of zero or more inputs.

- Each macro file optionally defines an outputs macro, which will create CloudFormation outputs based upon a set of zero or more inputs.

Current resource types supported include:

- Network - defined in [`network.j2`](./macros/network.j2).  This creates resources and outputs for creating all standard networking resources and outputs.

### Using Macros

To use macros, include the following declaration at the top of your CloudFormation template (i.e. `templates/stack.yml.j2`):

```
{% import 'macros/network.j2' as network with context %}
...
...
```

You can then call macros via the `network` variable in the example above:

```
{% import 'macros/network.j2' as network with context %}
...
...
Resources:
{{ network.resources(config_vpc_id, config_vpc_cidr, config_vgw_id) }}

Outputs:
{{ network.outputs(config_vpc_id, config_vpc_cidr) }}
...
```

## Examples

### Invoking the Role

The following is an example of a playbook configured to use this role.  Note the use of the [AWS STS role](git@github.com:Casecommons/aws-sts.git) to obtain STS credentials is separate from this role.

```
---
- name: STS Assume Role Playbook
  hosts: "{{ env }}"
  gather_facts: no
  environment:
  vars:
    Sts:
      Role: arn:aws:iam::123456789:role/admin
      Region: us-west-2
  roles:
  - aws_sts

- name: Stack Deployment Playbook
  hosts: "{{ env }}"
  environment: "{{ sts_creds }}"
  roles:
    - aws-cloudformation
```

## Release Notes

### Version 2.5.3

- **NEW FEATURE**: Add support for overrides using JMESPath queries

### Version 2.5.2

- **BUG FIX**: Fix issue where stack deployment failures return a success exit code - see [Ansible issue](https://github.com/ansible/ansible/issues/31543#issuecomment-390455919)

### Version 2.5.1

- **BUG FIX**: Ensure template and config files are unique when stack name is same across multiple environments

### Version 2.5.0

- **ENHANCEMENT**: Compatible with Ansible 2.5
- **BUG FIX**: Ensure S3 URL is used when upload to S3 is configured

### Version 2.4.2

- **ENHANCEMENT**: Add `Stack.BuildFolder` variable for setting build output during template generation

### Version 2.4.1

- **BUG FIX**: Disable stack policy only if an active stack currently exists

### Version 2.4.0

- **BREAKING CHANGE** : Compatibility fixes for Ansible 2.4.x
- **ENHANCEMENT** : Refactor datetime fact to remove requirement to gather Ansible facts
- **ENHANCEMENT** : Add `Stack.Facts` and `Stack.Url` variables
- **ENHANCEMENT** : Add service role support
- **ENHANCEMENT** : Remove jq dependency

### Version 0.9.5

- **ENHANCEMENT** : Include stack tags with generated `config.json` files

### Version 0.9.4

- **BUG FIX** : Removed jinja references to Stack.Name in template s3.yml.j2 since it is redundant and susceptible to breakage `./templates/s3.yml/j2`

### Version 0.9.3

- **NEW FEATURE** : Added generic [cloudfront template](`https://github.com/Casecommons/aws-cloudformation/pull/2`)
- **NEW FEATURE** : Added generic [s3 template](`https://github.com/Casecommons/aws-cloudformation/pull/4`)
- **ENHANCEMENT** : Updated jinja indentation on [ecr template](`https://github.com/Casecommons/aws-cloudformation/pull/4`)
- **NEW FEATURE** : Added generic [dns template](`https://github.com/Casecommons/aws-cloudformation/pull/7`)
- **NEW FEATURE** : Added generic CA [certificate template](`https://github.com/Casecommons/aws-cloudformation/pull/9`)

### Version 0.9.2

- **BUG FIX** : Output `config.json` with all values as strings (required for CodePipeline CloudFormation deployment support)

### Version 0.9.1

- **ENHANCEMENT** : Support list of default dependency mappings in stack transform feature
- **BUG FIX** : Fix issue where DependsOn property renaming for stack transform resource fails if component resource does not having existing DependsOn property

### Version 0.9.0

- **NEW FEATURE** : Added stack transforms, a new feature to support merging component templates into a master template
- **NEW FEATURE** : Added stack overrides, a new syntax to override portions of the stack template
- **BREAKING CHANGE** : Auto generated stack inputs now rely on the `Stack.Inputs` dictionary, and support the same dot notation naming scheme of stack overrides
- **ENHANCEMENT**: Add S3 bucket name exports to [CloudFormation template](`templates/cfn.yml.j2`)

### Version 0.8.0

- **NEW FEATURE** : Auto generate stack inputs from CloudFormation template parameters
- **NEW FEATURE** : Add ability to disable stack rollback

### Version 0.7.0

- **NEW FEATURE** : Add [security template](`templates/security.yml.j2`)
- **BUG FIX** : Fix harded coded AZ count in [network template](`templates/network.yml.j2`)
- **ENHANCEMENT** : Add ability to specify AZ count in [proxy template](`templates/proxy.yml.j2`)
- **ENHANCEMENT** : Use native CloudFormation log group resorces in [proxy template](`templates/proxy.yml.j2`)

### Version 0.6.1

- **ENHANCEMENT** : Update [proxy template](`templates/proxy.yml.j2`) autoscaling update policy to match input desired count
- **ENHANCEMENT** : Add whitelist support for [proxy template](`templates/proxy.yml.j2`)
- **ENHANCEMENT** : Add disable whitelist support for [proxy template](`templates/proxy.yml.j2`)
- **ENHANCEMENT** : Add support for VPC Flow Logs to [network template]('templates/network.yml.j2')

### Version 0.6.0

- **ENHANCEMENT** : Output `config.json` build artifact compatible with AWS CodePipeline CloudFormation Deployment
- **ENHANCEMENT** : Add support for configuring public and/or private route 53 zones to [network template](`templates/network.yml.j2`)

### Version 0.5.0

- **ENHANCEMENT** : Add KMS key to [CloudFormation template](`templates/cfn.yml.j2`)

### Version 0.4.0

- **ENHANCEMENT** : Add `cf_stack_facts` output
- **BUG FIX** : Fix missing substituion in proxy template

### Version 0.3.1

- **BUG FIX** : Set Proxy template ELB idle timeout to 120 seconds to avoid ECS agent disconnections

### Version 0.3.0

- **ENHANCEMENT** : Add proxy stack template
- **ENHANCEMENT** : Add support for creating a default VPC domain in network template
- **ENHANCEMENT** : Add CloudFormation resources template

### Version 0.2.0

- **ENHANCEMENT** : Add EC2 Container Registry (ECR) template

### Version 0.1.1

- **BUG FIX** : Fix issue where playbook will exit with success code even if a failure occurs
- **ENHANCEMENT** : Add Subnet CIDRs as exported outputs

### Version 0.1.0

- First Release

## License

Copyright (C) 2017.  Case Commons, Inc.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

See www.gnu.org/licenses/agpl.html
