# Copyright (C) 2023 Haiko Schol
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
import logging
import os
import kopf
import kubernetes
import yaml


# stages of an ORT run
ANALYZER, SCANNER, REPORTER = 'analyzer', 'scanner', 'reporter'

# job templates
TEMPLATES = {
    ANALYZER: f'{ANALYZER}-job.yaml',
    SCANNER: f'{SCANNER}-job.yaml',
    REPORTER: f'{REPORTER}-job.yaml',
}

# possible job states for each stage
PENDING, CREATED, RUNNING, SUCCEEDED, FAILED, ABORTED = 'Pending', 'Created', 'Running', 'Succeeded', 'Failed', 'Aborted'


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.posting.level = logging.ERROR


@kopf.on.create('ortruns')
def create_fn(name, namespace, spec, patch, **_):
    repo_url = spec.get('repoUrl')
    if not repo_url:
        raise kopf.PermanentError('OrtRun needs a repoUrl')

    create_job(ANALYZER, name, namespace, repo_url)

    patch.status[ANALYZER] = CREATED
    patch.status[SCANNER] = PENDING
    patch.status[REPORTER] = PENDING


def is_modified(event, **_):
    return event.get('type', '') == 'MODIFIED'


@kopf.on.event('batch', 'v1', 'jobs', annotations={'ortStage': kopf.PRESENT}, when=is_modified)
def handle_job_status_change(meta, body, logger, **_):
    stage = meta.annotations['ortStage']
    stage_status = get_stage_status(body.get('status', {}))
    repo_url = body.get('spec', {}).get('repoUrl', '')
    _, parent_name = meta.name.split('-', 1)

    update_ortrun_status(parent_name, meta.namespace, stage, stage_status)

    if stage_status == SUCCEEDED:
        next_stage = SCANNER if stage == ANALYZER else REPORTER if stage == SCANNER else None
        if next_stage:
            create_job(next_stage, parent_name, meta.namespace, repo_url)
            update_ortrun_status(parent_name, meta.namespace, next_stage, CREATED)

    elif stage_status == FAILED and stage != REPORTER:
        update_ortrun_status(parent_name, meta.namespace, REPORTER, ABORTED)
        if stage == ANALYZER:
            update_ortrun_status(parent_name, meta.namespace, SCANNER, ABORTED)


def get_stage_status(job_status):
    if job_status.get('failed', 0) > 0:
        return FAILED

    if job_status.get('succeeded', 0) > 0:
        return SUCCEEDED

    if job_status.get('active', 0) > 0:
        return RUNNING

    return PENDING


def create_job(stage, parent_name, namespace, repo_url):
    path = os.path.join(os.path.dirname(__file__), TEMPLATES[stage])
    name = f'{stage}-{parent_name}'

    with open(path, 'rt') as f:
        tmpl = f.read()
        text = tmpl.format(name=name, parent_name=parent_name, repo_url=repo_url)
        data = yaml.safe_load(text)

    kopf.adopt(data)
    api = kubernetes.client.BatchV1Api()
    return api.create_namespaced_job(namespace, data)


def update_ortrun_status(name, namespace, stage, status):
    api = kubernetes.client.CustomObjectsApi()

    try:
        api.patch_namespaced_custom_object('inocybe.io', 'v1', namespace, 'ortruns', name, {'status': {stage: status}})
    except kubernetes.client.exceptions.ApiException:
        raise kopf.PermanentError(f'updating status of run "{name}" for stage "{stage}" to "{status}" failed')
