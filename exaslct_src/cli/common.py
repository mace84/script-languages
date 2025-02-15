import getpass
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Tuple, Set

import luigi
import networkx
from networkx import DiGraph

from exaslct_src.lib.stoppable_task import StoppableTask
from exaslct_src.lib.task_dependency import TaskDependency, DependencyState


def set_build_config(force_rebuild: bool,
                     force_rebuild_from: Tuple[str, ...],
                     force_pull: bool,
                     log_build_context_content: bool,
                     output_directory: str,
                     temporary_base_directory: str,
                     cache_directory: str):
    luigi.configuration.get_config().set('build_config', 'force_rebuild', str(force_rebuild))
    luigi.configuration.get_config().set('build_config', 'force_rebuild_from', json.dumps(force_rebuild_from))
    luigi.configuration.get_config().set('build_config', 'force_pull', str(force_pull))
    set_output_directory(output_directory)
    if temporary_base_directory is not None:
        luigi.configuration.get_config().set('build_config', 'temporary_base_directory', temporary_base_directory)
    if cache_directory is not None:
        luigi.configuration.get_config().set('build_config', 'cache_directory', cache_directory)
    luigi.configuration.get_config().set('build_config', 'log_build_context_content', str(log_build_context_content))


def set_output_directory(output_directory):
    if output_directory is not None:
        luigi.configuration.get_config().set('build_config', 'output_directory', output_directory)


def set_docker_repository_config(docker_password: str, docker_repository_name: str, docker_username: str, tag_prefix: str,
                                 kind: str):
    config_class = f'{kind}_docker_repository_config'
    luigi.configuration.get_config().set(config_class, 'tag_prefix', tag_prefix)
    if docker_repository_name is not None:
        luigi.configuration.get_config().set(config_class, 'repository_name', docker_repository_name)
    if docker_username is not None:
        if docker_password is not None:
            luigi.configuration.get_config().set(config_class, 'username', docker_username)
            luigi.configuration.get_config().set(config_class, 'password', docker_password)
        else:
            password = getpass.getpass(f"{kind.capitalize()} Docker Registry Password for User %s:" % docker_username)
            luigi.configuration.get_config().set(config_class, 'username', docker_username)
            luigi.configuration.get_config().set(config_class, 'password', password)


def import_build_steps(flavor_path: Tuple[str, ...]):
    # We need to load the build steps of a flavor in the commandline processor,
    # because the imported classes need to be available in all processes spawned by luigi.
    # If we use, import the build steps in a Luigi Task they are only available in the worker
    # which executes this task. The build method with local scheduler of luigi uses fork
    # to create the scheduler and worker processes, such that the imported classes available
    # in the scheduler and worker processes
    import importlib.util
    for path in flavor_path:
        path_to_build_steps = Path(path).joinpath("flavor_base/build_steps.py")
        module_name_for_build_steps = path.replace("/", "_").replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name_for_build_steps, path_to_build_steps)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


# TODO add watchdog, which uploads the logs after given ammount of time, to get logs before travis kills the job
def run_tasks(tasks_creator: Callable[[], List[luigi.Task]],
              workers: int, task_dependencies_dot_file: str,
              on_success: Callable[[], None] = None,
              on_failure: Callable[[], None] = None):
    setup_worker()
    start_time = datetime.now()
    tasks = remove_stoppable_task_targets(tasks_creator)
    no_scheduling_errors = luigi.build(tasks, workers=workers, local_scheduler=True, log_level="INFO")
    if StoppableTask().failed_target.exists() or not no_scheduling_errors:
        handle_failure(on_failure)
    else:
        handle_success(on_success, task_dependencies_dot_file, start_time)


def handle_success(on_success: Callable[[], None], task_dependencies_dot_file: str, start_time: datetime):
    generate_graph_from_task_dependencies(task_dependencies_dot_file)
    if on_success is not None:
        on_success()
    timedelta = datetime.now() - start_time
    print("The command took %s s" % timedelta.total_seconds())
    exit(0)


def generate_graph_from_task_dependencies(task_dependencies_dot_file: str):
    if task_dependencies_dot_file is not None:
        print(f"Generate Task Dependency Graph to {task_dependencies_dot_file}")
        print()
        dependencies = collect_dependencies()
        g = DiGraph()
        for dependency in dependencies:
            g.add_node(dependency.source, label=dependency.source.representation)
            g.add_node(dependency.target, label=dependency.target.representation)
            g.add_edge(dependency.source, dependency.target,
                       dependency=dependency,
                       label=f"\"type={dependency.type}, index={dependency.index}\"")
        networkx.nx_pydot.write_dot(g, task_dependencies_dot_file)


def collect_dependencies() -> Set[TaskDependency]:
    stoppable_task = StoppableTask()
    dependencies = set()
    for root, directories, files in os.walk(stoppable_task.dependencies_dir):
        for file in files:
            file_path = Path(root).joinpath(file)
            with open(file_path) as f:
                for line in f.readlines():
                    task_dependency = TaskDependency.from_json(line)
                    if task_dependency.state == DependencyState.requested.name:
                        dependencies.add(task_dependency)
    return dependencies


def handle_failure(on_failure: Callable[[], None]):
    if on_failure is not None:
        on_failure()
    exit(1)


def remove_stoppable_task_targets(tasks_creator):
    stoppable_task = StoppableTask()
    if stoppable_task.failed_target.exists():
        stoppable_task.failed_target.remove()
    if stoppable_task.timers_dir.exists():
        shutil.rmtree(str(stoppable_task.timers_dir))
    if stoppable_task.dependencies_dir.exists():
        shutil.rmtree(str(stoppable_task.dependencies_dir))
    tasks = tasks_creator()
    return tasks


def setup_worker():
    luigi.configuration.get_config().set('worker', 'wait_interval', str(0.1))
    luigi.configuration.get_config().set('worker', 'wait_jitter', str(0.5))


def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options
