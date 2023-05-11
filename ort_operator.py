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


@kopf.on.create('ortruns')
def create_fn(name, namespace, spec, patch, **_):
    repo_url = spec.get('repoUrl')
    if not repo_url:
        raise kopf.PermanentError('OrtRun needs a repoUrl')

    create_job(ANALYZER, name, namespace, repo_url)

    patch.metadata.annotations['inProgress'] = '1'
    patch.status[ANALYZER] = CREATED
    patch.status[SCANNER] = PENDING
    patch.status[REPORTER] = PENDING


# HACK FIXME there must be a way of tracking the jobs using handlers instead of timers
@kopf.timer('ortruns', interval=1, annotations={'inProgress': kopf.PRESENT})
def check_jobs(name, namespace, body, patch, **_):
    spec = get_resource_attr('spec', body)
    repo_url = spec.get('repoUrl')
    if not repo_url:
        raise kopf.PermanentError('OrtRun {name} somehow lost its repoUrl')

    status = get_resource_attr('status', body)

    if status[ANALYZER] in (CREATED, RUNNING):
        job = get_job(ANALYZER, name, namespace)
        js = get_job_status(job)
        patch.status[ANALYZER] = js

        if js == FAILED:
            patch.status[SCANNER] = ABORTED
            patch.status[REPORTER] = ABORTED

    elif status[ANALYZER] == SUCCEEDED and status[SCANNER] == PENDING:
        create_job(SCANNER, name, namespace, repo_url)
        patch.status[SCANNER] = CREATED

    elif status[SCANNER] in (CREATED, RUNNING):
        job = get_job(SCANNER, name, namespace)
        js = get_job_status(job)
        patch.status[SCANNER] = js

        if js == FAILED:
            patch.status[REPORTER] = ABORTED

    elif status[SCANNER] == SUCCEEDED and status[REPORTER] == PENDING:
        create_job(REPORTER, name, namespace, repo_url)
        patch.status[REPORTER] = CREATED

    elif status[REPORTER] in (CREATED, RUNNING):
        job = get_job(REPORTER, name, namespace)
        patch.status[REPORTER] = get_job_status(job)

    if status[REPORTER] in (SUCCEEDED, FAILED, ABORTED):
        patch.metadata.annotations['inProgress'] = None


def get_job(stage, parent_name, namespace):
    name = f'{stage}-{parent_name}'
    api = kubernetes.client.BatchV1Api()

    try:
        job = api.read_namespaced_job(name, namespace)
    except kubernetes.client.exceptions.ApiException:
        raise kopf.PermanentError(f'job with name "{name}" not found')

    return job


def get_job_status(job):
    if job.status.failed is not None and job.status.failed > 0:
        return FAILED
    if job.status.succeeded is not None and job.status.succeeded > 0:

        return SUCCEEDED
    if job.status.active is not None and job.status.active > 0:
        return RUNNING
    return CREATED


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


def get_resource_attr(attr, body):
    val = body.get(attr)

    if not val:
        raise kopf.PermanentError(f'resource has no {attr}. got {val!r}')

    return val
