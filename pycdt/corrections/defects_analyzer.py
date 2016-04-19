#!/usr/bin/env python


__author__ = "Geoffroy Hautier, Bharat Medasani"
__copyright__ = "Copyright 2014, The Materials Project"
__version__ = "1.0"
__maintainer__ = "Geoffroy Hautier, Bharat Medasani"
__email__ = "geoffroy@uclouvain.be, mbkumar@gmail.com"
__status__ = "Development"
__date__ = "November 4, 2012"

from math import sqrt, floor, pi, exp
from collections import defaultdict 
from itertools import combinations

import numpy as np

from pymatgen.core.structure import PeriodicSite
from pymatgen.io.vasp.outputs import Locpot
from pymatgen.entries.computed_entries import ComputedStructureEntry
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from pycdt.corrections.finite_size_charge_correction import ChargeCorrection

#some constants
kb = 8.6173324e-5
hbar = 6.58211928e-16
conv = sqrt((9.1*1e-31)**3)*sqrt((1.6*1e-19)**3)/((1.05*1e-34)**3)

class ParsedDefect(object):
    """
    Holds all the info concerning a defect computation: 
    composition+structure, energy, correction on energy and name
    """
    def __init__(self, entry_defect, site_in_bulk, charge=0.0,
                 charge_correction=0.0, name=None):
        """
        Args:
            entry_defect: 
                An Entry object corresponding to the defect
            charge: 
                The charge of the defect
            charge_correction: 
                Some correction to the energy due to charge
            name: 
                The name of the defect
        """

        self.entry = entry_defect
        self.site = site_in_bulk
        self._charge = charge
        self.charge_correction = charge_correction # Can be added after initialization
        self._name = name
        self._full_name = self._name + "_" + str(charge)

    def as_dict(self):
        return {'entry': self.entry.as_dict(),
                'site': self.site.as_dict(),
                'charge': self._charge,
                'charge_correction': self.charge_correction,
                'name': self._name,
                'full_name': self._full_name,
                '@module': self.__class__.__module__,
                '@class': self.__class__.__name__}

    @classmethod
    def from_dict(cls, d):
        return ParsedDefect(
                ComputedStructureEntry.from_dict(d['entry']), 
                PeriodicSite.from_dict(d['site']),
                charge=d.get('charge',0.0),
                charge_correction=d.get('charge_correction',0.0),
                name=d.get('name',None))


def get_correction_freysoldt(defect, bulk_entry, epsilon, title = None):
    """
    Function to compute the correction for each defect.
    Args:
        defect: ParsedDefect object
        bulk_entry: ComputedStructureEntry corresponding to bulk
        epsilon: dielectric constant
    """
    if type(bulk_entry) is Locpot:
        locpot_blk = bulk_entry
        locpot_path_blk = 'fakepath' #this doesnt matter if Locpot is already loaded
    else:
        locpot_blk = None
        locpot_path_blk = bulk_entry.data['locpot_path']
    locpot_path_def = defect.entry.data['locpot_path']
    charge = defect._charge
    #frac_coords = defect.site.frac_coords  #maybe can use this later...but not neccessary?
    encut = defect.entry.data['encut']

    corr_meth = ChargeCorrection(epsilon,
            locpot_path_blk, locpot_path_def, charge,
            pure_locpot = locpot_blk, #for quicker loading of bulk locpot objects...
            energy_cutoff = encut,
            silence=False)
    #if either locpot already loaded then load pure_locpot= or defect_locpot=
    # if you want to load position then can load it with pos=
    #if want to to change energy tolerance for correction convergence then change madetol= (default is 0.0001)
    # (for kumagai) if known optgamma, set optgamma=, if KumagaiBulk already initialized then set KumagaiBulk=?

    corr_val = corr_meth.freysoldt(title=title, axis=0, partflag='All') #could do an averaging over three axes but this works for now...

    #return sum(corr_val)/len(corr_val)
    return (corr_val,corr_meth._purelocpot)


def get_correction_kumagai(defect, bulk_init, epsilon_tensor):
    """
    --------------------------------------------------------------
    TODO: Make easy way to store KumagaiBulk object for doing several successive Kumagai calculations?
    TODO: allow for bulk_init input to be a string to bulkLocpot so that you can build
    --------------------------------------------------------------
    Function to compute the correction for each defect.
    Args:
        defect: ParsedDefect object
        bulk_init: KumagainBulkInit class object
        epsilon_tensor: Dielectric tenson
        type: 
            "freysoldt": Freysoldt correction for isotropic crystals
            "kumagai": modified Freysoldt or Kumagai for anisotropic crystals
    """
    #locpot_path_blk = bulk_entry.data['locpot_path']
    locpot_path_blk = ""#bulk_entry.data['locpot_path'] #should fix this
    epsilon = bulk_init.epsilon
    locpot_path_def = defect.entry.data['locpot_path']
    charge = defect._charge
    #frac_coords = defect.site.frac_coords  #maybe can use this later...but not neccessary?
    encut = defect.entry.data['encut']

    corr_meth = ChargeCorrection(epsilon_tensor,
            locpot_path_blk, locpot_path_def, charge,
            energy_cutoff = encut,
            silence=False, KumagaiBulk=bulk_init)
    #if either locpot already loaded then load pure_locpot= or defect_locpot=
    # if you want to load position then can load it with pos=
    #if want to to change energy tolerance for correction convergence then change madetol= (default is 0.0001)
    # (if known optgamma, set optgamma=, if KumagaiBulk already initialized then set KumagaiBulk=

    corr_val = corr_meth.kumagai(title=defect._full_name, partflag='All') #should probably split this up to include

    return corr_val


class DefectsAnalyzer(object):
    """
    a class aimed at performing standard analysis of defects
    """
    def __init__(self, entry_bulk, e_vbm, mu_elts, band_gap):
        """
        Args:
            entry_bulk:
                the bulk data as an Entry
            e_vbm:
                the energy of the vbm (in eV)
            mu_elts:
                a dictionnary of {Element:value} giving the chemical
                potential of each element
            band_gap:
                the band gap (in eV)
        """
        self._entry_bulk = entry_bulk
        self._e_vbm = e_vbm
        self._mu_elts = mu_elts
        self._band_gap = band_gap
        self._defects = []
        self._formation_energies = []

    def as_dict(self):
        d = {'entry_bulk': self._entry_bulk.as_dict(),
             'e_vbm': self._e_vbm,
             'mu_elts': self._mu_elts,
             'band_gap': self._band_gap,
             'defects': [d.as_dict() for d in self._defects],
             'formation_energies': self._formation_energies,
             "@module": self.__class__.__module__,
             "@class": self.__class__.__name__}
        return d

    @classmethod
    def from_dict(cls, d):
        entry_bulk = ComputedStructureEntry.from_dict(d['entry_bulk'])
        analyzer = DefectsAnalyzer(
                entry_bulk, d['e_vbm'], 
                {el: d['mu_elts'][el] for el in d['mu_elts']}, d['band_gap'])
        for ddict in d['defects']:
            analyzer.add_defect(ParsedDefect.from_dict(ddict))
        return analyzer

    def add_parsed_defect(self, defect):
        """
        add a parsed defect to the analyzer
        Args:
            defect:
                a Defect object
        """
        self._defects.append(defect)
        self._compute_form_en()

    def change_charge_correction(self, i, correction):
        """
        Change the charge correction for defect at index i
        Args:
            i:
                Index of defects
            correction:
                New correction to be applied for defect
        """
        self._defects[i].charge_correction = correction
        self._compute_form_en()

    def _get_all_defect_types(self):
        to_return = []
        for d in self._defects:
            if d._name not in to_return: to_return.append(d._name)
        return to_return

    def _compute_form_en(self):
        """
        compute the formation energies for all defects in the analyzer
        """
        self._formation_energies = []
        for d in self._defects:
            #compensate each element in defect with the chemical potential
            mu_needed_coeffs = {}
            for elt in d.entry.composition.elements:
                el_def_comp = d.entry.composition[elt] 
                el_blk_comp = self._entry_bulk.composition[elt]
                mu_needed_coeffs[elt] = el_blk_comp - el_def_comp

            sum_mus = 0.0
            for elt in mu_needed_coeffs:
                el = elt.symbol
                sum_mus += mu_needed_coeffs[elt] * self._mu_elts[el]

            self._formation_energies.append(
                    d.entry.energy - self._entry_bulk.energy + \
                            sum_mus + d._charge*self._e_vbm + \
                            d.charge_correction)

    def correct_bg_simple(self, vbm_correct, cbm_correct):
        """
        correct the band gap in the analyzer.
        We assume the defects level remain the same when moving the 
        band edges
        Args:
            vbm_correct:
                The correction on the vbm as a positive number. e.g., 
                if the VBM goes 0.1 eV down vbm_correct=0.1
            cbm_correct:
                The correction on the cbm as a positive number. e.g., 
                if the CBM goes 0.1 eV up cbm_correct=0.1

        """
        self._band_gap = self._band_gap + cbm_correct + vbm_correct
        self._e_vbm = self._e_vbm - vbm_correct
        self._compute_form_en()

    def get_transition_levels(self):
        xlim = (-0.5, self._band_gap+1.5)
        nb_steps = 1000
        x = np.arange(xlim[0], xlim[1], (xlim[1]-xlim[0])/nb_steps)
 
        y = defaultdict(defaultdict)
        for i, dfct in enumerate(self._defects):
            yval = self._formation_energies[i] + dfct._charge*x
            y[dfct._name][dfct._charge] = yval

        transit_levels = defaultdict(defaultdict)
        for dfct_name in y:
            q_ys = y[dfct_name]
            for qpair in combinations(q_ys.keys(),2):
                #if abs(qpair[1]-qpair[0]) == 1:
                y_absdiff = abs(q_ys[qpair[1]] - q_ys[qpair[0]])
                if y_absdiff.min() < 0.4: 
                    transit_levels[dfct_name][qpair] = x[np.argmin(y_absdiff)]
        return transit_levels


    def correct_bg(self, dict_levels, vbm_correct, cbm_correct):
        """
        correct the band gap in the analyzer and make sure the levels move
        accordingly.
        There are two types of defects vbm_like and cbm_like and we need
        to provide a formal oxidation state
        The vbm-like will follow the vbm and the cbm_like the cbm. If nothing
        is specified the defect transition level does not move
        Args:
            dict_levels: a dictionnary of type {defect_name:
            {'type':type_of_defect,'q*':formal_ox_state}}
            Where type_of_defect is a string: 'vbm_like' or 'cbm_like'
        """


        self._band_gap = self._band_gap + cbm_correct + vbm_correct
        self._e_vbm = self._e_vbm - vbm_correct
        self._compute_form_en()
        for i in range(len(self._defects)):
            name = self._defects[i]._name
            if not name in dict_levels:
                continue

            if dict_levels[name]['type'] == 'vbm_like':
                z = self._defects[i]._charge - dict_levels[name]['q*']
                self._formation_energies[i] += z * vbm_correct
            if dict_levels[name]['type'] == 'cbm_like':
                z = dict_levels[name]['q*'] - self._defects[i]._charge
                self._formation_energies[i] +=  z * cbm_correct


    def _get_form_energy(self, ef, i):
        return self._formation_energies[i] + self._defects[i]._charge*ef

    def get_defects_concentration(self, temp=300, ef=0.0):
        """
        get the defect concentration for a temperature and Fermi level
        Args:
            temp:
                the temperature in K
            Ef:
                the fermi level in eV (with respect to the VBM)
        Returns:
            a list of dict of {'name': defect name, 'charge': defect charge 
                               'conc': defects concentration in m-3}
        """
        conc=[]
        spga = SpacegroupAnalyzer(self._entry_bulk.structure, symprec=1e-1)
        struct = spga.get_symmetrized_structure()
        i = 0
        for d in self._defects:
            df_coords = d.site.frac_coords
            target_site=None
            #TODO make a better check this large tol. is weird
            for s in struct.sites:
                sf_coords = s.frac_coords
                if abs(s.frac_coords[0]-df_coords[0]) < 0.1 \
                        and abs(s.frac_coords[1]-df_coords[1]) < 0.1 \
                        and abs(s.frac_coords[2]-df_coords[2]) < 0.1:
                    target_site=s
                    break
            equiv_site_no = len(struct.find_equivalent_sites(target_site))
            n = equiv_site_no * 1e30 / struct.volume
            conc.append({'name': d._name, 'charge': d._charge,
                         'conc': n*exp(
                             -self._get_form_energy(ef, i)/(kb*temp))})
            i += 1
        return conc

    def _get_dos(self, e, m1, m2, m3, e_ext):
        return sqrt(2) / (pi**2*hbar**3) * sqrt(m1*m2*m3) * sqrt(e-e_ext)

    def _get_dos_fd_elec(self, e, ef, t, m1, m2, m3):
        return conv * (2.0/(exp((e-ef)/(kb*t))+1)) * \
               (sqrt(2)/(pi**2)) * sqrt(m1*m2*m3) * \
               sqrt(e-self._band_gap)

    def _get_dos_fd_hole(self, e, ef, t, m1, m2, m3):
        return conv * (exp((e-ef)/(kb*t))/(exp((e-ef)/(kb*t))+1)) * \
               (2.0 * sqrt(2)/(pi**2)) * sqrt(m1*m2*m3) * \
               sqrt(-e)

    def _get_qd(self, ef, t):
        summation = 0.0
        for d in self.get_defects_concentration(t, ef):
            summation += d['charge'] * d['conc']
        return summation

    def _get_qi(self, ef, t, m_elec, m_hole):
        from scipy import integrate as intgrl

        elec_den_fn = lambda e: self._get_dos_fd_elec(
                e, ef, t, m_elec[0], m_elec[1], m_elec[2])
        hole_den_fn = lambda e: self._get_dos_fd_hole(
                e, ef, t, m_hole[0], m_hole[1], m_hole[2])

        bg = self._band_gap
        elec_count = -intgrl.quad(elec_den_fn, bg, bg+5)[0]
        hole_count = intgrl.quad(hole_den_fn, -5, 0.0)[0]

        return el_cnt + hl_cnt

    def _get_qtot(self, ef, t, m_elec, m_hole):
        return self._get_qd(ef, t) + self._get_qi(ef, t, m_elec, m_hole)

    def get_eq_ef(self, t, m_elec, m_hole):
        """
        access to equilibrium values of Fermi level and concentrations 
        in defects and carriers obtained by self-consistent solution of 
        charge balance + defect and carriers concentrations
        Args:
            t: temperature in K
            m_elec: electron effective mass as a 3 value list 
                    (3 eigenvalues for the tensor)
            m_hole:: hole effective mass as a 3 value list 
                    (3 eigenvalues for the tensor)
        Returns:
            a dict with {
                'ef':eq fermi level,
                'Qi': the concentration of carriers
                      (positive for holes, negative for e-) in m^-3,
                'conc': the concentration of defects as a list of dicts
                }
        """
        from scipy.optimize import bisect
        e_vbm = self._e_vbm
        e_cbm = self._e_vbm+self._band_gap
        ef = bisect(lambda e:self._get_qtot(e,t,m_elec,m_hole), 0, 
                self._band_gap)
        return {'ef': ef, 'Qi': self._get_qi(ef, t, m_elec, m_hole),
                'QD': self._get_qd(ef,t), 
                'conc': self.get_defects_concentration(t, ef)}

    def get_non_eq_ef(self, tsyn, teq, m_elec, m_hole):
        """
        access to the non-equilibrium values of Fermi level and 
        concentrations in defects and carriers obtained by 
        self-consistent solution of charge balance + defect and 
        carriers concentrations

        Implemented following Sun, R., Chan, M. K. Y., Kang, S., 
        and Ceder, G. (2011). doi:10.1103/PhysRevB.84.035212

        Args:
            tsyn: the synthesis temperature in K
            teq: the temperature of use in K
            m_elec: electron effective mass as a 3 value list 
                    (3 eigenvalues for the tensor)
            m_hole: hole effective mass as a 3 value list 
                    (3 eigenvalues for the tensor)
        Returns:
            a dict with {
                'ef':eq fermi level,
                'Qi': the concentration of carriers
                      (positive for holes, negative for e-) in m^-3,
                'conc': the concentration of defects as a list of dict
                }
        """
        from scipy.optimize import bisect
        eqsyn = self.get_eq_ef(tsyn, m_elec, m_hole)
        cd = {}
        for c in eqsyn['conc']:
            if c['name'] in cd:
                cd[c['name']] += c['conc']
            else:
                cd[c['name']] = c['conc']
        ef = bisect(lambda e:self._get_non_eq_qtot(cd, e, teq, m_elec, m_hole),
                    -1.0, self._band_gap+1.0)
        return {'ef':ef, 'Qi':self._get_qi(ef, teq, m_elec, m_hole),
                'conc_syn':eqsyn['conc'],
                'conc':self._get_non_eq_conc(cd, ef, teq)}

    def _get_non_eq_qd(self, cd, ef, t):
        sum_tot = 0.0
        for n in cd:
            sum_d = 0.0
            sum_q = 0.0
            i = 0
            for d in self._defects:
                if d._name == n:
                    sum_d += exp(-self._get_form_energy(ef, i)/(kb*t))
                    sum_q += d._charge * exp(
                            -self._get_form_energy(ef, i)/(kb*t))
                i += 1
            sum_tot += cd[n]*sum_q/sum_d
        return sum_tot

    def _get_non_eq_conc(self, cd, ef, t):
        sum_tot = 0.0
        res=[]
        for n in cd:
            sum_tot = 0
            i = 0
            for d in self._defects:
                if d._name == n:
                    sum_tot += exp(-self._get_form_energy(ef,i)/(kb*t))
                i += 1
            i=0
            for d in self._defects:
                if d._name == n:
                    res.append({'name':d._name,'charge':d._charge,
                                'conc':cd[n]*exp(-self._get_form_energy(
                                    ef,i)/(kb*t))/sum_tot})
                i += 1
        return res

    def _get_non_eq_qtot(self, cd, ef, t, m_elec, m_hole):
        return self._get_non_eq_qd(cd, ef, t) + \
               self._get_qi(ef, t, m_elec, m_hole)
