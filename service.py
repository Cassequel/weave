"""Bounded, cancellable local conversion jobs. Exports are the previewed bytes."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from uuid import uuid4

from preparation import prepare
from inkstitch_backend import digitize


class DesignService:
    def __init__(self, worker=digitize):
        self.worker = worker
        self.prepared = OrderedDict()
        self.jobs = OrderedDict()
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def prepare(self, image, settings):
        result = prepare(image, settings)
        key = uuid4().hex
        result['preparationId'] = key
        with self.lock:
            self.prepared[key] = result
            while len(self.prepared) > 8: self.prepared.popitem(last=False)
        return result

    def start(self, key):
        with self.lock:
            if key not in self.prepared: raise ValueError('Prepared artwork has expired. Prepare the image again.')
            if sum(j['status'] in ('queued','running') for j in self.jobs.values()) >= 2:
                raise ValueError('Another conversion is waiting. Cancel it or wait for it to finish.')
            while len(self.jobs) >= 10:
                old = next((k for k,j in self.jobs.items() if j['status'] not in ('queued','running')),None)
                if old is None: break
                del self.jobs[old]
            job_id = uuid4().hex
            job = dict(status='queued',cancel=Event(),prepared=self.prepared[key])
            self.jobs[job_id] = job
        self.pool.submit(self._run,job_id,job)
        return job_id

    def _run(self,key,job):
        try:
            with self.lock: job['status'] = 'running'
            if job['cancel'].is_set():
                with self.lock: job['status'] = 'cancelled'
                return
            result,pes = self.worker(job['prepared'],job['cancel'])
            with self.lock:
                if job['cancel'].is_set(): job['status'] = 'cancelled'
                else: job.update(status='complete',result={**result,'designId':key},pes=pes)
        except Exception as exc:
            with self.lock: job.update(status='cancelled' if job['cancel'].is_set() else 'failed',error=str(exc))

    def status(self,key):
        with self.lock:
            if key not in self.jobs: raise ValueError('Conversion has expired. Generate stitches again.')
            return {k:self.jobs[key][k] for k in ('status','result','error') if k in self.jobs[key]}

    def cancel(self,key):
        with self.lock:
            if key in self.jobs: self.jobs[key]['cancel'].set()

    def pes(self,key):
        with self.lock:
            job = self.jobs.get(key)
            if not job or job['status'] != 'complete': raise ValueError('No completed design to export.')
            return job['pes']

    def svg(self,key):
        with self.lock:
            if key not in self.prepared: raise ValueError('Prepared artwork has expired.')
            return self.prepared[key]['svg'].encode('utf-8')

    def close(self):
        with self.lock:
            for job in self.jobs.values(): job['cancel'].set()
        self.pool.shutdown(wait=True)
