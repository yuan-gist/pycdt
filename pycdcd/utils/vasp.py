#!/usr/bin/env python

"""
TODO create a VaspInputSet instead?
"""

__author__ = "Geoffroy Hautier, Bharat Medasani"
__copyright__ = "Copyright 2014, The Materials Project"
__version__ = "1.0"
__maintainer__ = "Geoffroy Hautier"
__email__ = "geoffroy@uclouvain.be"
__status__ = "Development"
__date__ = "November 4, 2012"

from pymatgen.io.vaspio.vasp_input import Kpoints
from pymatgen.io.vaspio_set import MPVaspInputSet
from monty.serialization import loadfn, dumpfn
from monty.json import MontyDecoder, MontyEncoder

#import json
import os

def make_vasp_defect_files(defects, path_base, user_settings=None, 
                           hse=False):
    """
    Generates VASP files for defect computations
    Args:
        defect_structs:
            the defects data as a dictionnary. Ideally this is generated
            from core.defectsmaker.ChargedDefectsStructures.
        path_base:
            where we write the files
        user_settings:
            Settings in dict format to override the defaults used in 
            generating vasp files. The format of the dictionary is
            {'incar':{...},
             'kpoints':...}
        hse:
            hse run or not
    """
    bulk_sys = defects['bulk']
    comb_defs = reduce(lambda x,y: x+y, [
        defects[key] for key in defects if key != 'bulk'])

    for defect in comb_defs:
        for charge in defect['charges']:
            s = defect['supercell']
            dict_transf={
                    'defect_type': defect['name'], 
                    'defect_site': defect['unique_site'], 
                    'charge': charge, 'supercell': s['size']}

            dict_params=MPVaspInputSet().get_all_vasp_input(s['structure'])
            incar=dict_params['INCAR']
            incar.update({'IBRION':2,'ISIF':2,'ISPIN':2,'LWAVE':False,
                'EDIFF':1e-5,'EDIFFG':-1e-2,'ISMEAR':0,'SIGMA':0.05, 
                'LVTOT':True,'LVHAR':True,'LORBIT':11,'ALGO':"Fast"})
            if hse == True:
                incar.update({'LHFCALC':True,"ALGO":"All","HFSCREEN":0.2,
                    "PRECFOCK":"Fast","AEXX":0.45})

            comp=s['structure'].composition
            sum_elec=0
            elts=set()
            for p in dict_params['POTCAR']:
                if p.element not in elts:
                    sum_elec+=comp.to_dict[p.element]*p.nelectrons
                    elts.add(p.element)
            if charge != 0:
                incar['NELECT']=sum_elec-charge

            kpoint=Kpoints.monkhorst_automatic()

            path=os.path.join(path_base,defect['name'],"charge"+str(charge))
            os.makedirs(path)
            incar.write_file(os.path.join(path,"INCAR"))
            kpoint.write_file(os.path.join(path,"KPOINTS"))
            dict_params['POSCAR'].write_file(os.path.join(path,"POSCAR"))
            dict_params['POTCAR'].write_file(os.path.join(path,"POTCAR"))
            dumpfn(dict_transf,os.path.join(path,'transformations.json'),
                    cls=MontyEncoder)

    # Generate bulk supercell inputs
    s = bulk_sys
    dict_transf={
            'defect_type': 'bulk', 
            'supercell': s['supercell']['size']}

    dict_params=MPVaspInputSet().get_all_vasp_input(s['structure'])
    incar=dict_params['INCAR']
    incar.update({'IBRION':-1,"NSW":0,'ISPIN':2,'LWAVE':False,'EDIFF':1e-5,
        'ISMEAR':0,'SIGMA':0.05,'LVTOT':True,'LVHAR':True,'ALGO':'Fast'})
    if hse == True:
        incar.update({'LHFCALC':True,"ALGO":"All","HFSCREEN":0.2,
            "PRECFOCK":"Fast","AEXX":0.45})
    kpoint=Kpoints.monkhorst_automatic()
    path=os.path.join(path_base,'bulk')
    os.makedirs(path)
    incar.write_file(os.path.join(path,"INCAR"))
    kpoint.write_file(os.path.join(path,"KPOINTS"))
    dict_params['POSCAR'].write_file(os.path.join(path,"POSCAR"))
    dict_params['POTCAR'].write_file(os.path.join(path,"POTCAR"))
    dumpfn(dict_transf,os.path.join(path,'transformations.json'),
            cls=MontyEncoder)

def make_vasp_dielectric_files(struct, user_settings=None, hse=False):
    """
    Generates VASP files for dielectric constant computations
    Args:
        struct:
            unitcell in pymatgen structure format 
        user_settings:
            Settings in dict format to override the defaults used in 
            generating vasp files. The format of the dictionary is
            {'incar':{...},
             'kpoints':...}
        hse:
            hse run or not
    """

    # Generate vasp inputs for dielectric constant

    dict_params=MPVaspInputSet().get_all_vasp_input(s['structure'])
    incar=dict_params['INCAR']
    incar.update({"NSW":0,'ISPIN':2,'LWAVE':False,'EDIFF':1e-5,
        'ISMEAR':0,'SIGMA':0.05,'ALGO':'Fast'})
    incar.update({'IBRION':8,'LEPSILON':True,'LEPAD':True})
    if hse == True:
        incar.update({'LHFCALC':True,"ALGO":"All","HFSCREEN":0.2,
            "PRECFOCK":"Fast","AEXX":0.45})
    path_base = struct.composition.reduced_formula
    path=os.path.join(path_base,'dielectric')
    os.makedirs(path)
    incar.write_file(os.path.join(path,"INCAR"))
    kpoint.write_file(os.path.join(path,"KPOINTS"))
    dict_params['KPOINTS'].write_file(os.path.join(path,"KPOINTS"))
    dict_params['POSCAR'].write_file(os.path.join(path,"POSCAR"))
    dict_params['POTCAR'].write_file(os.path.join(path,"POTCAR"))
