"""The logs variant's read-only plane (docs/variants.md, Live logs).

Two stdlib-only programs that render into the variant's own images, never into the runtime or harness image:

  collect.py  the `obs` sidecar inside the cluster: copies complete read-only views (scheduler state, daemon logs,
              node counters, the store's listing, the engine's status) into the `obs` volume every few seconds; it
              takes no input from anyone
  tools.py    the workstation's squeue, sinfo, scontrol, sacct, ocb, ... answered from those views; commands that would
              change the cluster or need a shell on it say they are not available

The workstation has no network path to the cluster, so the views are the only way anything about the cluster reaches
the agent, and nothing the agent does reaches the cluster.
"""
