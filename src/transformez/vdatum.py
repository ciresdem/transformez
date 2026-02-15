#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
transformez.vdatum
~~~~~~~~~~~~~

This wraps the NGS 'VDatum' tool.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import logging

from . import utils

logger = logging.getLogger(__name__)

vdatum_cmd = 'vdatum.jar -v'
HAS_VDATUM = utils.cmd_check('vdatum.jar', vdatum_cmd).decode()

## ==============================================
## NOAA's VDATUM Wrapper
## ==============================================
class Vdatum:
    def __init__(self, jar=None, ivert='navd88:m:height', overt='mhw:m:height',
                 ihorz='NAD83_2011', ohorz='NAD83_2011', region='4', fmt='txt',
                 xyzl='0,1,2', skip=0, delim='space', result_dir='result',
                 verbose=False):
        self.jar = jar
        self.ivert = ivert
        self.overt = overt
        self.ihorz = ihorz
        self.ohorz = ohorz
        self.region = region
        self.fmt = fmt
        self.xyzl = xyzl
        self.skip = skip
        self.delim = delim
        self.result_dir = result_dir
        self.verbose = verbose
        self.epoch = None
        self.vdatum_set_horz()

        
    def vdatum_set_horz(self):
        if 'ITRF' in self.overt:
            self.ohorz = self.overt
            self.epoch = '1997.0:1997.0'

            
    def vdatum_locate_jar(self):
        """Find the VDatum executable on the local system."""
        
        results = []
        for root, dirs, files in os.walk('/'):
            if 'vdatum.jar' in files:
                results.append(os.path.abspath(os.path.join(root, 'vdatum.jar')))
                break
        if not results:
            return None
        else:
            self.jar = results[0]
            return results

        
    def vdatum_get_version(self):
        """Run vdatum and attempt to get its version."""
        
        if self.jar is None:
            self.vdatum_locate_jar()
        if self.jar is not None:
            out, _ = utils.run_cmd(f'java -jar {self.jar} -', verbose=self.verbose)
            for i in out.decode('utf-8').split('\n'):
                if '- v' in i.strip():
                    return i.strip().split('v')[-1]
        return None

    
    def vdatum_xyz(self, xyz):
        """Run vdatum on an xyz list [x, y, z]."""
        
        if self.jar is None:
            self.vdatum_locate_jar()
        if self.jar is not None:
            epoch_str = f'epoch:{self.epoch} ' if self.epoch is not None else ''
            vdc = (f'ihorz:{self.ihorz} ivert:{self.ivert} ohorz:{self.ohorz} overt:{self.overt} '
                   f'-nodata -pt:{xyz[0]},{xyz[1]},{xyz[2]} {epoch_str}region:{self.region}')
            
            out, _ = utils.run_cmd(
                f'java -Djava.awt.headless=false -jar {self.jar} {vdc}',
                verbose=False
            )
            z = xyz[2]
            for i in out.split('\n'):
                if 'Height/Z' in i:
                    try:
                        z = float(i.split()[2])
                        break
                    except ValueError:
                        pass
            return [xyz[0], xyz[1], z]
        else: 
            return xyz

        
    def vdatum_clean_result(self):
        """Clean the vdatum 'result' folder."""
        
        utils.remove_glob(f'{self.result_dir}/*')
        try:
            os.removedirs(self.result_dir)
        except OSError: 
            pass

        
    def run_vdatum(self, src_fn):
        """Run vdatum on src_fn which is an XYZ file."""
        
        if self.jar is None:
            self.vdatum_locate_jar()
        if self.jar is not None:
            epoch_str = f'epoch:{self.epoch} ' if self.epoch is not None else ''
            vdc = (f'ihorz:{self.ihorz} ivert:{self.ivert} ohorz:{self.ohorz} overt:{self.overt} '
                   f'-nodata -file:txt:{self.delim},{self.xyzl},skip{self.skip}:{src_fn}:{self.result_dir} '
                   f'{epoch_str}region:{self.region}')
            return utils.run_cmd(f'java -jar {self.jar} {vdc}', verbose=self.verbose)
        else: 
            return [], -1
