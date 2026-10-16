"""Prepare a NEW local equation edition. Never overwrite a source or prior edition."""

import argparse
import collections
import shutil
from pathlib import Path

from principia_asd.catalog.audit import expanded_size
from principia_asd.catalog.equation_sources import READERS
from principia_asd.engine.equations import validate
from principia_asd.engine.transport_templates import TEMPLATES
from principia_asd.io import file_sha, read_csv, read_json, sha, write_csv, write_json

DESCRIPTIONS = {
 '013': ('Thermally activated encapsulant cure', 'Compare depletion and autocatalytic pathways across complete heating scans. The response is a measured calorimetric conversion rate, conditional on the source-derived conversion coordinate. Author-fitted curves are excluded.'),
 '027': ('Vapor transport and radial phase distribution', 'Connect vapor and liquid superficial velocities, phase drift and radial redistribution to measured local void fraction. Density calculations are disclosed fixed physical preprocessing.'),
 '043': ('Learning dynamics beyond early checkpoints', 'Use two disclosed early checkpoints to compare asymptotic loss decay and a capacity-dependent decay law on held-out architectures. The inferred loss floor is a conditional quantity, not measured data entropy.'),
 '049': ('Diffusion and polarization during battery rest', 'Compare finite-pulse diffusion and effective exponential polarization relaxation using the same early voltage anchors. Complete later rest blocks remain held out.'),
 '061': ('Gas transport through a porous membrane', 'Separate molecule-wall and viscous transport contributions to nitrogen flux through a hydrotalcite-coated support. Entire temperature regimes are held out, with calibrated absolute pressures and source flux units.'),
 '069': ('Frictional heating in a robot gearbox', 'Predict the next minute of lubricant-temperature change from measured friction power and thermal boundaries. A thermal resistance network competes with a speed-dependent mixing hypothesis; no future control measurements are inputs.'),
 '074': ('Saturation dynamics of a kinase biosensor', 'Compare effective first-order and dose-modulated assay responses after a short disclosed fluorescence calibration. Signal amplitudes remain instrument units, not inferred molecular concentrations.'),
 '082': ('Forest-soil respiration across sites', 'Compare thermal activation, water limitation and root-exclusion associations using soil measurements from complete held-out sites. The task retains site heterogeneity and does not identify causal effects of management.'),
}
NEW_UNITS = {
 '013': {'temperature':'K','conversion':'1','heating_rate':'K/s','target':'s^-1'},
 '061': {'temperature':'K','pressure_feed':'Pa','pressure_permeate':'Pa','target':'mol/m2/s'},
 '069': {'lubricant_temperature':'K','housing_temperature':'K','environment_temperature':'K','speed':'rad/s','torque':'N*m','horizon':'s','target':'K'},
 '082': {'temperature':'K','water_fraction':'1','root_exclusion':'1','target':'kg/m2/s'},
}
MEANINGS = {
 '013': {'temperature':'Measured scan temperature in kelvin','conversion':'Author-derived calorimetric conversion fraction; coupled to the same measured heat signal','heating_rate':'Programmed heating rate, converted from Celsius/minute to kelvin/second','target':'Calorimetric conversion rate, converted from percent/minute to fraction/second'},
 '061': {'temperature':'Measured membrane temperature in kelvin','pressure_feed':'Retentate absolute pressure in pascals','pressure_permeate':'Permeate absolute pressure in pascals','target':'Source-reported nitrogen molar flux per membrane area'},
 '069': {'lubricant_temperature':'Lubricant temperature at the forecast start','housing_temperature':'Housing temperature at the forecast start','environment_temperature':'Environment temperature at the forecast start','speed':'Measured motor angular velocity at the forecast start','torque':'Measured friction torque at the forecast start','horizon':'Elapsed time to the 60-second future observation','target':'Observed lubricant temperature change over the forecast horizon'},
 '082': {'temperature':'Measured soil temperature at 5 cm, converted to kelvin','water_fraction':'Volumetric water content, converted from percent to fraction','root_exclusion':'Source trenching indicator: 1 for root exclusion, 0 otherwise','target':'Author-derived chamber CO2 mass flux, converted from g CO2/m2/hour to kg CO2/m2/second'},
}
POLICIES = {
 '013': 'Whole heating scans: train 1/5/10 Celsius per minute; dev 3; test 20. One encapsulant system; heating-rate transfer, not independent-batch replication.',
 '061': 'Single S-HT membrane and nitrogen only. Whole nominal temperatures: train 25/200/500 Celsius; dev 350; test 300/400/450. Actual temperatures remain inputs. Source validation sheet and other gases/materials are outside this contract.',
 '069': 'Source identification runs train except 1.4137 rad/s dev; every source validation run is test. Nonoverlapping 60-second windows; instantaneous start-state inputs only. Single robot joint.',
 '082': 'Whole site families. Dev Llobera/Secanella/St Christol; test Gamiz/Kacergine/Kranzberg-Freising/Saint Mitre/RincondelBatovi; remaining eligible sites train. Adjacent Karstula and Dumbravita families never cross partitions.',
}
OLD_MAPS = {
 '027': {'mass_flux':('massflux_kg_m2_s',1,'kg/m2/s','Measured mixture mass flux'), 'quality':('quality',1,'1','Source outlet mass quality'), 'vapor_density':('rho_vapor',1,'kg/m3','Fixed pressure-derived IAPWS vapor density'), 'liquid_density':('rho_liquid',1,'kg/m3','Fixed pressure-derived IAPWS liquid density'), 'radial_fraction':('radial_fraction',1,'1','Native radial coordinate divided by its sampled maximum; not a verified tube-radius fraction')},
 '043': {'tokens':('tokens_B',1,'1','Training tokens in the fixed billion-token coordinate'), 'anchor_tokens':('anchor_tokens_B',1,'1','Later disclosed calibration checkpoint in billion tokens'), 'early_tokens':('early_tokens_B',1,'1','Earlier disclosed calibration checkpoint in billion tokens'), 'anchor_loss':('anchor_loss',1,'1','Later disclosed calibration validation loss'), 'early_loss':('early_loss',1,'1','Earlier disclosed calibration validation loss'), 'model_size':('params_B',1,'1','Model parameter count in billions')},
 '049': {'elapsed':('t',1,'s','Elapsed rest time at the forecast horizon'), 'anchor_time_early':('t60',1,'s','Actual earlier disclosed rest-calibration time'), 'anchor_time_late':('t120',1,'s','Actual later disclosed rest-calibration time'), 'voltage_early':('u60',1,'V','Measured earlier disclosed rest voltage'), 'voltage_late':('u120',1,'V','Measured later disclosed rest voltage'), 'pulse_duration':('pulse_s',1,'s','Duration of the completed preceding current pulse')},
 '074': {'concentration':('concentration_uM',0.001,'mol/m3','Source biosensor dose converted from micromolar'), 'elapsed':('time_min',60,'s','Assay observation time from the protocol start'), 'initial_signal':('calibration_F6',1,'a.u.','Disclosed six-minute fluorescence observation'), 'initial_slope':('calibration_v6',1/60,'a.u./s','Disclosed early finite-difference fluorescence slope')},
}
OUTPUT_UNITS = {'027':'1','043':'1','049':'V','074':'a.u.'}


def prepare(raw, output, vault, historical, old_vault, project):
    if output.exists() or vault.exists():
        raise ValueError('Choose new immutable output and evaluator directories')
    registry = {x['case_id']:x for x in read_json(raw/'_benchmark_100/CATALOG.json')}
    output.mkdir(parents=True); vault.mkdir(parents=True)
    audits=[]
    for case in TEMPLATES:
        sid='P100-'+case; meta=registry[sid]; source_root=raw/meta['local_folder']
        title, description=DESCRIPTIONS[case]
        info_extra={}; provenance_extra={}
        if case in READERS:
            rows, rejected, sources=READERS[case](source_root)
            units, meanings=NEW_UNITS[case],MEANINGS[case]
            policy=POLICIES[case]
        else:
            base=historical/'scenarios'/sid; old=read_json(base/'task-contracts/task-001.json')
            mapping=OLD_MAPS[case]; units={k:v[2] for k,v in mapping.items()}|{'target':OUTPUT_UNITS[case]}
            meanings={k:v[3] for k,v in mapping.items()}|{'target':old.get('title','Measured response')}
            targets={r['sample_id']:r for r in read_csv(old_vault/sid/'test_targets.csv.gz')}
            rows=[]
            for part in ['train','dev','test']:
                for r in read_csv(base/old['split'][part]):
                    target=targets[r['sample_id']]['target'] if part=='test' else r['target']
                    rows.append(dict(sample_id=r['sample_id'],group=r['group'],partition=part,
                                     source_coordinate='historical-sample:'+r['sample_id'],
                                     **{k:float(r[v[0]])*v[1] for k,v in mapping.items()},target=float(target)))
            rejected=[]
            recipe=read_json(project/f'configs/preparation/{sid}.raw-v1.json')
            release_raw=raw/'_benchmark_100/release_candidate'
            sources=[]
            for a in recipe['assets']:
                src=release_raw/a['path']
                if file_sha(src)!=a['sha256']:raise ValueError('Native source hash changed: '+str(src))
                sources.append({'path':str(src.relative_to(raw)),'sha256':a['sha256'],'bytes':src.stat().st_size})
            info_extra={'extends_scenario_sha256':file_sha(base/'scenario.json'), 'extends_task_sha256':file_sha(base/'task-contracts/task-001.json')}
            provenance_extra={'historical_contract_sha256':file_sha(base/'task-contracts/task-001.json'),
                              'native_recipe':recipe, 'projection':{k:{'source':v[0],'factor':v[1]} for k,v in mapping.items()},
                              'historical_partition_hashes':{k:file_sha(base/old['split'][k]) for k in ['train','dev','test']},
                              'preservation':'All historical samples and target values preserved. Only permitted inputs are selected and explicitly converted. No refitting or label-dependent filtering.'}
            policy=recipe.get('policy',{}).get('split',recipe.get('partition_provenance',{}).get('allocation','Original complete-group splits preserved'))
        root=output/'scenarios'/sid; private=vault/sid
        task={'scenario_id':sid,'task_id':sid+'.mechanisms-v2','revision':2,
              'title':title,'display_title':title,'description':description,
              'inputs':[k for k in units if k!='target'],'output':'target','quantity_units':units,
              'variable_descriptions':meanings,'metric':{'primary':'mae','aggregation':'equal_group_mean'},
              'split':{k:f"public/{'test_inputs' if k=='test' else k}.csv.gz" for k in ['train','dev','test']},
              'stability':{'domain':'Native measured domain; bounded perturbations of continuous inputs only',
                           'ranking':False,'relative_noise':0.01,'categorical_inputs':['root_exclusion'] if case=='082' else [],
                           'scope':'Diagnostic sensitivity; source-calibrated measurement-error distributions unavailable'},
              'test_exposure':'retrospective-open-test','equation_templates':TEMPLATES[case](),
              'split_policy':policy,'scientific_scope':'Constitutive hypotheses and matched predictive tests; no novelty, causality or independent discovery claim',
              'preprocessing':{'learned_transformations':[], 'native_reading':'Deterministic coordinate and SI conversions; source-derived responses explicitly identified'},
              'equation_protocol':'multi-role-equations-v2'}
        reference = {'043':'anchor_loss', '049':'voltage_late', '069':'0', '074':'initial_signal'}.get(case)
        if reference:
            task['reference_expression'] = reference
        for t in task['equation_templates']:validate(t,task)
        parts={k:[r for r in rows if r['partition']==k] for k in ['train','dev','test']}
        if any(not p for p in parts.values()):raise ValueError('Empty partition '+sid)
        groups={k:sorted({r['group'] for r in data}) for k,data in parts.items()}
        if any(set(groups[a])&set(groups[b]) for a,b in [('train','dev'),('train','test'),('dev','test')]):raise ValueError('Group overlap '+sid)
        if len({r['sample_id'] for r in rows})!=len(rows):raise ValueError('Duplicate sample identity')
        for k,data in parts.items():
            fields=['sample_id','group',*task['inputs']]+([] if k=='test' else ['target'])
            write_csv(root/task['split'][k],[{f:r[f] for f in fields} for r in data],fields)
        write_csv(private/'test_targets.csv.gz',[{f:r[f] for f in ['sample_id','group','target']} for r in parts['test']],['sample_id','group','target'])
        write_json(private/'excluded-records.json',rejected,immutable=True)
        write_json(root/'task-contracts/task-001.json',task,immutable=True)
        write_json(private/'evaluator-manifest.json',{'task_id':task['task_id'],'scenario_id':sid,
                   'input_sha256':file_sha(root/task['split']['test']), 'target_sha256':file_sha(private/'test_targets.csv.gz'),
                   'contract_sha256':file_sha(root/'task-contracts/task-001.json'),'version':'equation-assessment-v2'},immutable=True)
        lineage=[{'sample_id':r['sample_id'],'group':r['group'],'source_coordinate':r['source_coordinate']} for r in rows]
        write_csv(root/'provenance/lineage.csv.gz',lineage,list(lineage[0]))
        limitations=list(dict.fromkeys([a for t in task['equation_templates'] for a in t['assumptions']]))
        audit={'scenario_id':sid,'rows':{k:len(v) for k,v in parts.items()},'groups':groups,'split_policy':policy,
               'excluded_count':len(rejected),'exclusion_reasons':dict(collections.Counter(r['reason'] for r in rejected)),
               'sources':sources,'registry_entry_sha256':sha(meta),'test_targets_public':False,
               'source_terms':meta['license_or_terms'],'source_url':meta['source_url'],
               'admission':'local_research_preview','scientific_review':'not_assessed',**provenance_extra}
        write_json(root/'provenance/preparation.json',audit,immutable=True)
        info={'scenario_id':sid,'title':title,'description':description,'domain':meta['domain'],
              'edition':'mechanism-pack-v2','status':'local_research_preview','local_extension':True,
              'rows':audit['rows'],'limitations':limitations,'independent_unit':policy,
              'source':{'url':meta['source_url'],'license':meta['license_or_terms'],'registry_identity':sid},
              'rights_status':'source_terms_recorded; final_publication_review_pending','publication_authorized':False,
              'size':{'public_bytes':sum(f.stat().st_size for f in root.rglob('*') if f.is_file())},**info_extra}
        write_json(root/'scenario.json',info,immutable=True)
        (root/'README.md').write_text(f'# {title}\n\n{description}\n\n## Scientific contract\n\n{policy}\n\n'+
                                     '\n'.join('- '+x for x in limitations)+f"\n\nSource: {meta['source_url']}\n\nTerms: {meta['license_or_terms']}\n\nThe pack-level builder reconstructs this version. Native source hashes and row lineage are recorded. Test targets remain in the separate evaluator vault. Known equation families are disclosed priors.\n")
        write_json(root/'checksums.json',{str(f.relative_to(root)):file_sha(f) for f in sorted(root.rglob('*')) if f.is_file()},immutable=True)
        size=sum(expanded_size(f) for f in root.rglob('*') if f.is_file())
        if size>10_000_000:raise ValueError('Expanded package exceeds 10 MB '+sid)
        audits.append({'scenario_id':sid,'new_scenario':case in READERS,'title':title,'rows':audit['rows'],'groups':{k:len(v) for k,v in groups.items()},'expanded_bytes':size})
        print(audits[-1],flush=True)
    write_json(output/'EDITION.json',{'version':'1.0.0rc6','edition':'mechanism-pack-v2','scenarios':audits,'publication_authorized':False},immutable=True)
    shutil.copyfile(__file__,output/'prepare.py')
    (output/'README.md').write_text('# Connected scientific models — local edition\n\nFour new scientific examples and four additional tasks for existing scenarios. Each task compares explicit scientific hypotheses with numerical controls. Historical tasks and results remain unchanged.\n\nRun `prepare.py --help` with the matching principia-asd package. The source manifest, native coordinates, split policy and limitations live in every scenario. Public files exclude test targets. Independent scientific review and final redistribution clearance remain pending.\n')
    return audits


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ['raw','output','vault','historical','old-vault','project']:
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    prepare(args.raw,args.output,args.vault,args.historical,args.old_vault,args.project)
