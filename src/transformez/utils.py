#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.utils
~~~~~~~~~~~~~

This holds various utility functions.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import subprocess
import logging

logger = logging.getLogger(__name__)

def run_cmd(args):
    """Standalone replacement for utils.run_cmd using subprocess."""
    
    logger.info(f'Running: {" ".join(args) if isinstance(args, list) else args}')
    
    result = subprocess.run(
        args, 
        shell=False if isinstance(args, list) else True, 
        capture_output=True, 
        text=True
    )
    return result.stdout, result.returncode

cmd_exists = lambda x: any(os.access(os.path.join(path, x), os.X_OK) 
                           for path in os.environ['PATH'].split(os.pathsep))

def cmd_check(cmd_str, cmd_vers_str):
    """check system for availability of 'cmd_str'"""
        
    if cmd_exists(cmd_str): 
        cmd_vers, status = run_cmd(f'{cmd_vers_str}')
        return cmd_vers.rstrip()
    return b"0"
