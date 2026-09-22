"""Public study tools protect input evidence and preserve failure denominators."""
import json

import pytest

from mapf.api import check_run_bundle, check_solver
from mapf.application.studies import create_study, experiment_card
from mapf.core.models import Point, SimulationConfig
from mapf.solvers.base import MAPFInstance
from mapf.solvers.registry import get_solver


def test_study_creation_is_headless_portable_and_never_overwrites(tmp_path):
    destination=tmp_path/'a study'
    result=create_study(destination, name='A researcher study')
    assert result['directory']==str(destination.resolve())
    spec=json.loads((destination/'study.json').read_text())
    assert spec['sampling']['generalization']=='none; teaching fixtures only'
    assert (destination/'run.py').exists() and (destination/'analyze.py').exists()
    assert (destination/'maps/README.md').exists()
    (destination/'user.txt').write_text('keep')
    with pytest.raises(FileExistsError):create_study(destination)
    assert (destination/'user.txt').read_text()=='keep'
    link=tmp_path/'linked';link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(FileExistsError):create_study(link)


def test_invalid_scaffold_has_no_side_effect(tmp_path):
    target=tmp_path/'bad'
    with pytest.raises(ValueError):create_study(target,name='')
    assert not target.exists()


def test_experiment_card_requires_all_planned_rows_and_keeps_unsolved():
    from mapf.application.experiments import compile_experiment
    manifest=compile_experiment({'name':'test', 'scenarios':[{'scenario_id':'crossing-2a'}], 'matrix':{'solver_id':['CBS','Prioritized']}})
    rows=[{'trial_id':t['trial_id'],'experiment_id':manifest['experiment_id'],'source_sha256':manifest['source_sha256'],
           'state':s,'success':s=='completed','validation_status':'valid_solution' if s=='completed' else 'not_checked'}
          for t,s in zip(manifest['trials'],['completed','timed_out'],strict=True)]
    card=experiment_card(manifest,rows)
    assert card['outcomes']['planned']==2 and card['outcomes']['valid_solutions']==1
    assert card['outcomes']['success_rate']==.5 and card['hardware'] is None
    assert card['paper_reproduction']=='not established by this card'
    for broken in [rows[:1], rows+[rows[0]], [dict(rows[0],source_sha256='wrong'),rows[1]]]:
        with pytest.raises(ValueError):experiment_card(manifest,broken)
    rows[1]['success']=True
    with pytest.raises(ValueError):experiment_card(manifest,rows)


def test_public_solver_check_accepts_existing_method_and_rejects_fabricated_cost():
    instance=MAPFInstance(grid_width=3,grid_height=3,starts={'a':Point(0,0)},goals={'a':Point(2,0)})
    config=SimulationConfig(grid_width=3,grid_height=3)
    solver=get_solver('CBS')
    assert check_solver(solver,instance,config)['status']=='valid_solution'
    class WrongCost:
        name=solver.name
        is_centralized=True
        def solve(self,instance,config):
            return solver.solve(instance,config).model_copy(update={'sum_of_costs':999})
    with pytest.raises(ValueError,match='cost'):check_solver(WrongCost(),instance,config)
    class Mutates:
        name=solver.name
        is_centralized=True
        def solve(self,instance,config):
            instance.starts['a']=Point(0,1)
            return solver.solve(instance,config)
    with pytest.raises(ValueError,match='mutat'):check_solver(Mutates(),instance,config)


def test_bundle_contract_rejects_version_and_checksum():
    with pytest.raises(ValueError,match='version'):check_run_bundle({'format':'decmapf-run','version':'future'})
    with pytest.raises(ValueError,match='checksum'):check_run_bundle({'format':'decmapf-run','version':'1.0','payload':{},'sha256':'wrong'})


def test_conformance_retains_legitimate_no_path_failure_without_claiming_valid_prefix():
    from mapf.core.hashing import compute_instance_hash
    from mapf.solvers.base import MAPFSolution
    instance=MAPFInstance(grid_width=3,grid_height=3,starts={'a':Point(0,0)},goals={'a':Point(2,0)})
    config=SimulationConfig(grid_width=3,grid_height=3)
    class NoCandidate:
        name='no-candidate-fixture'
        is_centralized=True
        def solve(self,instance,config):
            return MAPFSolution(solver_name=self.name,is_centralized=True,success=False,
                                instance_hash=compute_instance_hash(instance,config.setting))
    receipt=check_solver(NoCandidate(),instance,config)
    assert receipt['status']=='not_checked' and receipt['success'] is False
