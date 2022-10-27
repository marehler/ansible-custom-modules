#!/usr/bin/python

DOCUMENTATION = '''
---
module: summarize_static_routes
short_description: Checks candidate static routes for existing summary routes.
description:
  - This module compares a list of candidate static routes with existing routes,
    and removes candidate routes from the list for which a summary static route
    already exists on the target device. The output of this module can be used as
    input to the cisco.ios.ios_static_routes module for configuration. 
options:
  existing_config:
    description:
    - List of static routes as returned by the cisco.ios.ios_static_routes module
      with state 'parsed'.
    required: True
  candidate_config:
    description:
    - List of static routes to be checked and summarized if applicable. Uses the same
      format as the 'config' options of the cisco.ios.ios_static_routes module.
    required: True
version: 0.1
author: Martin Ehlers (marehler@cisco.com)
'''
EXAMPLES = '''
# Before:

# csr1000v-1#show running-config | include ip route|ipv6 route
# ip route 0.0.0.0 0.0.0.0 GigabitEthernet1 10.10.20.254
# ip route 193.168.44.0 255.255.255.128 10.10.20.20
# ip route 193.168.44.128 255.255.255.128 10.10.20.20
# ip route 193.168.45.0 255.255.255.0 10.10.20.20
# ip route 193.168.46.0 255.255.255.0 10.10.20.20

# Playbook Tasks:

- name: Step 1 - Get static route configuration
  cisco.ios.command:
    commands:
      - show running-config | include ip route|ipv6 route
    register: ios_config
- name: Extract routes from response 
  ansible.builtin.set_fact:
    static_route_config: "{{ ios_config['stdout'][0] }}"  

- name: Step 2 - Transform config into structured Ansible data 
  cisco.ios.ios_static_routes:
    running_config: "{{ static_route_config }}"
    state: parsed
  register: config_parse_response 
- name: Extract routes from response 
  ansible.builtin.set_fact:
    existing_static_routes: "{{ config_parse_response['parsed'] }}"  

- name: Step 3 - Check for summary routes and remove sub-routes
  summarize_static_routes:
    existing_config: "{{ existing_static_routes }}"
    candidate_config:
    - address_families:
      - afi: ipv4
        routes:
        - dest: 193.168.42.0/30
          next_hops:
          - forward_router_address: 10.10.20.20
        - dest: 193.168.44.0/30
          next_hops:
          - forward_router_address: 10.10.20.20
  register: summary_check_response
- name: Extract summarized routes from response 
  ansible.builtin.set_fact:
    summarized_static_routes: "{{ summary_check_response['summarized_static_routes'] }}"  

- name: Step 4 - Configure static routes
  cisco.ios.ios_static_routes:
    config: "{{ summarized_static_routes }}"
  when: summarized_static_routes != []

# After:

# csr1000v-1#show running-config | include ip route|ipv6 route
# ip route 0.0.0.0 0.0.0.0 GigabitEthernet1 10.10.20.254
# ip route 193.168.42.0 255.255.255.252 10.10.20.20
# ip route 193.168.44.0 255.255.255.128 10.10.20.20
# ip route 193.168.44.128 255.255.255.128 10.10.20.20
# ip route 193.168.45.0 255.255.255.0 10.10.20.20
# ip route 193.168.46.0 255.255.255.0 10.10.20.20

# Note: The route to 193.168.44.0/30 has been removed by this module and not been
# configured as there is already a route for 193.168.44.0/25.
'''
RETURN = '''
summarized_static_routes:
  description:
  - List of routes based on the candidate_config input but with routes removed for
    which a summary static routes has been found.
'''


from ipaddress import IPv4Network, IPv6Network
from ansible.module_utils.basic import *


def check_if_subnet(candidate_dest, existing_dest, afi, summary_route_found):
    '''
    For a given IP candidate prefix and existing prefix pair, checks if the candidate
    prefix is a subnet, except for the default route. If it is a subnet, sets the
    summary_route_found flag to True. Otherwise it returns this flag as it was.
    '''
    if afi == 'ipv4':
        if existing_dest != '0.0.0.0/0':
            if IPv4Network(candidate_dest).subnet_of(IPv4Network(existing_dest)):
                summary_route_found = True
    elif afi == 'ipv6':
        if existing_dest != '::/0':
            if IPv6Network(candidate_dest).subnet_of(IPv6Network(existing_dest)):
                summary_route_found = True
    return summary_route_found

def remove_sub_routes(candidate, existing):
    '''
    Iterates over a list of candidate routes by VRF and address family. For every candidate route,
    finds existing routes for the respective VRF and address family, calls a function to check
    if the candidate prefix is a subnet of an existing prefix, and finally removes routes with
    destination prefixes that are a subnet of any such existing summary routes.
    '''
    changed = False
    # Iterate over VRFs
    for vrf in candidate:
        vrf_name = vrf.get('vrf', None)
        # Iterate over address families
        for af in vrf['address_families']:
            # Iterate over routes in 'candidate' and remove them if a summary route is found
            for candidate_route in reversed(af['routes']):
                summary_route_found = False
                # Iterate over routes in 'existing'
                # Default VRF case:
                if vrf_name is None:
                    # Find route item without VRF key
                    default_vrf = next((route for route in existing if 'vrf' not in route), None)
                    # Find routes of respective address family
                    default_af_routes = [route for route in default_vrf['address_families']
                        if route['afi'] == af['afi']]
                    for existing_route in default_af_routes:
                        # Check if candidate route is a subnet of existing route, except for default route
                        summary_route_found = check_if_subnet(candidate_route['dest'],
                        existing_route['routes'][0]['dest'], af['afi'], summary_route_found)
                # Non-default VRF case:
                else:
                    # Find and iterate over route items for respective VRF and address family
                    vrf_af_routes = [route for route in existing if 'vrf' in route
                        and route['vrf'] == vrf_name and route['address_families'][0]['afi'] == af['afi']]
                    for existing_route in vrf_af_routes:
                        # Check if candidate route is a subnet of existing route, except for default route
                        summary_route_found = check_if_subnet(candidate_route['dest'],
                            existing_route['address_families'][0]['routes'][0]['dest'], af['afi'],
                            summary_route_found)
                # Remove candidate route if existing summary route has been found
                if summary_route_found is True:
                    af['routes'].remove(candidate_route)
                    changed = True
        # Remove address family with empty route list 
        for af in list(vrf['address_families']):
            if len(af['routes']) == 0:
                vrf['address_families'].remove(af)
    # Remove VRFs with empty address family list
    for vrf in list(candidate):
        if len(vrf['address_families']) == 0:
            candidate.remove(vrf)
    return candidate, changed


def main():
    '''
    Main function
    '''
    # Create an AnsibleModule object and specify argument dictionary
    module = AnsibleModule(
        argument_spec = dict(
            existing_config = dict(required=True, type='list'),
            candidate_config = dict(required=True, type='list')
        )
    )
    # Call function to check for summary routes
    summarized_config, changed = remove_sub_routes(
        module.params['candidate_config'], module.params['existing_config'])
    # Return results
    module.exit_json(changed=changed, summarized_static_routes=summarized_config)

if __name__ == '__main__':
    main()
