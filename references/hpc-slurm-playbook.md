# HPC and Slurm Playbook

Use this when the SSH target is a login node, scheduler entrypoint, or managed research cluster rather than a single always-on Linux host.

Examples use the cross-platform Python entrypoint. On Windows, the equivalent PowerShell entrypoint is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 <subcommand> ...
```

## First principles

- login nodes and compute nodes are different roles
- a shell on a compute node is usually tied to a scheduler allocation
- file transfer, job submission, and long-running work often follow different paths
- treat scheduler state as part of connectivity diagnosis

## Read-only diagnosis

From the login node, prefer:

```bash
python3 ./scripts/sshops.py run \
  --alias <alias> \
  --command 'hostname && whoami && pwd && squeue -u $USER && sinfo -s' \
  --bash \
  --batch-mode
```

Useful checks:

- `hostname`
- `whoami`
- `pwd`
- `squeue -u $USER`
- `sinfo -s`
- `module avail` or `module list` when the cluster uses environment modules

## Batch jobs

Submit a job:

```bash
python3 ./scripts/sshops.py run \
  --alias <alias> \
  --remote-dir ~/project \
  --command "sbatch job.sh" \
  --bash \
  --batch-mode
```

Watch queue state:

```bash
python3 ./scripts/sshops.py run \
  --alias <alias> \
  --command 'squeue -u $USER' \
  --bash \
  --batch-mode
```

Collect logs after completion:

```bash
python3 ./scripts/sshops.py run \
  --alias <alias> \
  --remote-dir ~/project \
  --command "tail -n 200 slurm-<jobid>.out" \
  --bash \
  --batch-mode
```

## Interactive jobs

When the cluster requires an allocation before work can run:

```bash
python3 ./scripts/sshops.py run \
  --alias <alias> \
  --command "srun --pty bash -l" \
  --bash
```

Treat this as a different session class from the login node. Do not assume the compute-node shell survives after the allocation ends.

## Sync strategy

- sync code and input data to the login-node-visible storage path first
- avoid writing large outputs back through ad hoc chat-driven loops
- prefer pulling logs, summaries, and targeted artifacts unless the user explicitly wants full result sync

## Failure patterns worth calling out

- SSH is healthy but the scheduler has no capacity
- login-node SSH works but compute-node access requires an active allocation
- files are present on the login node but not on node-local scratch
- the shell environment on the login node differs from the batch-job environment

If the problem is "the job environment behaves differently from the login shell," diagnose it as a scheduler or environment issue, not an SSH issue.
