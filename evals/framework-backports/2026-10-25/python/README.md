These inputs add two Python library/issue pairs. The Pydantic import variants
describe the same issue and must be counted once. Neither advisory was published
within the six months preceding October 25, 2026.

Marshmallow checks one collection-merging performance component of
CVE-2025-68480. A child process loads 40,000 ordinary invalid records with a frozen
two-second CPU budget and checks that all indexed validation messages survive.
The expected CPU signal produces the security assertion; a wall timeout,
import error, crash or OOM remains unresolved. The selected fix precedes a
deepcopy compatibility adjustment included in the security releases, so this
case does not establish whole-CVE or complete-release remediation. The original
29-test ErrorStore suite and two ordinary controls also run.

Pydantic checks the historical CVE-2021-29510 fix under Python 3.9.25 using its
pure-Python implementation. Both normal controls and the original date parsing
suite run. The original importlib configuration fails 16 unchanged older-line
tests because that loader does not register their module in sys.modules.
The separately reviewed prepend configuration matches the original pytest 6.1.1
default; it changes no oracle, suite, image, source implementation or patch.
The original failed configurations remain part of the evidence.

All four revisions import staged source inside isolated containers; neither
evaluated distribution is installed into its dependency image. The source and
target implementation-only reference patches happen to be byte-identical for
both issues. Reference verification does not measure AI adaptation difficulty.

The `cases` directories contain frozen inputs and original MIT notices.
`proofs` records immutable revisions, release inclusion, independent clones,
the import-mode prerequisite and a corrected dependency-preparation mistake.
The first Pydantic image build selected a Python 2 wheel and failed before
target execution; its published Python 3 replacement has a separate recorded
hash. Runtime proofs record exact executed image IDs and staged module origins.

To rebuild Pydantic's dependency image, first download the hash-pinned pure-Python
wheels, then build with networking disabled. Run these commands from the
directory containing this README:

```sh
python -m pip download --no-deps --only-binary=:all: --platform any \
  --python-version 39 --implementation py --abi none --require-hashes \
  -r images/pydantic/requirements.txt -d images/pydantic/wheels
docker pull python@sha256:03dee9ce00747bb5390e7b4ad00307b4dbc7790f7da77cc3581f93cfa99a6363
docker build --network none --pull=false -t pydantic-date-evaluation:local images/pydantic
```

For Marshmallow, `Dockerfile.executed` records the exact local starting image and
offline dependency installation used in these runs. Its portable `Dockerfile`
starts from the pinned public Python image and reinstalls the recorded package
versions with hashes. This portable reconstruction has not been qualified:

```sh
docker build -t marshmallow-component-evaluation:local images/marshmallow
```

A rebuilt image has a new identity. Pin its actual ID into a copied harness
configuration and rerun the complete four-revision, repeat and ineffective-patch
checks before comparing results. Keep the recorded oracles and original tests
unchanged. The recorded checks cover the selected components, not either full
project suite or universal safety.
