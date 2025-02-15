from typing import Tuple

from click._unicodefun import click

from exaslct_src.cli.cli import cli
from exaslct_src.cli.common import set_build_config, set_docker_repository_config, run_tasks, add_options, import_build_steps
from exaslct_src.cli.options \
    import build_options, flavor_options, system_options, release_options, \
    docker_repository_options
from exaslct_src.lib.export_containers import ExportContainers


@cli.command()
@add_options(flavor_options)
@add_options(release_options)
@click.option('--export-path', type=click.Path(exists=False, file_okay=False, dir_okay=True), default=None)
@click.option('--release-name', type=str, default=None)
@add_options(build_options)
@add_options(docker_repository_options)
@add_options(system_options)
def export(flavor_path: Tuple[str, ...],
           release_type: str,
           export_path: str,
           release_name: str,
           force_rebuild: bool,
           force_rebuild_from: Tuple[str, ...],
           force_pull: bool,
           output_directory: str,
           temporary_base_directory: str,
           log_build_context_content: bool,
           cache_directory: str,
           source_docker_repository_name: str,
           source_docker_tag_prefix: str,
           source_docker_username: str,
           source_docker_password: str,
           target_docker_repository_name: str,
           target_docker_tag_prefix: str,
           target_docker_username: str,
           target_docker_password: str,
           workers: int,
           task_dependencies_dot_file: str):
    """
    This command exports the whole script language container package of the flavor,
    ready for the upload into the bucketfs. If the stages do not exists locally,
    the system will build or pull them before the exporting the packaged container.
    """
    import_build_steps(flavor_path)
    set_build_config(force_rebuild,
                     force_rebuild_from,
                     force_pull,
                     log_build_context_content,
                     output_directory,
                     temporary_base_directory,
                     cache_directory)
    set_docker_repository_config(source_docker_password, source_docker_repository_name, source_docker_username,
                                 source_docker_tag_prefix, "source")
    set_docker_repository_config(target_docker_password, target_docker_repository_name, target_docker_username,
                                 target_docker_tag_prefix, "target")
    tasks = lambda: [ExportContainers(flavor_paths=list(flavor_path),
                                      release_types=list([release_type]),
                                      export_path=export_path,
                                      release_name=release_name
                                      )]

    def on_success():
        with ExportContainers.command_line_output_target.open("r") as f:
            print(f.read())

    run_tasks(tasks, workers, task_dependencies_dot_file, on_success=on_success)
