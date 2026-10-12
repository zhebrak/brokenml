"""Task harness: provisioning, emulated infrastructure (object store) and the verifier.

Runs only in the harness image (the provisioning sidecar, the object store, the separate verifier). Nothing in this
package may be reachable from a container an agent can enter; `ocb` (the platform) must never import it.
"""
