# HPC and Slurm Playbook

Use this when the SSH target is a login node, scheduler entrypoint, or managed research cluster rather than a single always-on Linux host.

## First principles

- login nodes and compute nodes are different roles
- a shell on a compute node is usually tied to a scheduler allocation
- file transfer, job submission, and long-running work often follow different paths
- treat scheduler state as part of connectivity diagnosis

## Read-only diagnosis

From the login node, prefer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -Command "hostname && whoami && pwd && squeue -u $USER && sinfo -s" `
  -Bash `
  -BatchMode
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

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -RemoteDir ~/project `
  -Command "sbatch job.sh" `
  -Bash `
  -BatchMode
```

Watch queue state:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -Command "squeue -u $USER" `
  -Bash `
  -BatchMode
```

Collect logs after completion:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -RemoteDir ~/project `
  -Command "tail -n 200 slurm-<jobid>.out" `
  -Bash `
  -BatchMode
```

## Interactive jobs

When the cluster requires an allocation before work can run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -Command "srun --pty bash -l" `
  -Bash
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
