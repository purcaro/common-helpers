#!/bin/bash

ansible-playbook -i "localhost," -c local ssh_2fa.yml --ask-become-pass
