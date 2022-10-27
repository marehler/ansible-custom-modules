# Summarize Static Routes

## Description

This custom module compares a list of candidate static routes with existing routes, and removes candidate routes from the list for which a summary static route already exists on the target device. The output of this module can be used as input to the cisco.ios.ios_static_routes module for configuration.

## Documentation

Please refer to the built-in module documentation:

```
ansible-doc -M <path-to-module> summarize_static_routes
```
## Installation

To use the module only in a selected playbooks, store the module in a subdirectory called library in the directory that contains the playbooks.
```
.
|-- Summarize-routes-demo.yaml           <= playbook
|-- library
   |-- summarize_static_routes.py        <= module
```
To make the module available to all playbooks and roles, store it in one of the default Ansible module paths.

## Usage

Please refer to the sample playbook "Summarize-routes-demo.yaml".

```
ansible-playbook Summarize-routes-demo.yaml
```