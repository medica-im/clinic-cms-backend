# Requirements

`*.in` are the packages the backend asks for, with the version bounds it needs.
`*.txt` are generated from them by pip-compile: every package that gets
installed, transitive ones included, at an exact version. The Dockerfile
installs the `.txt` files, in this order: common, fastapi, development, test.
Each `.in` constrains itself to the ones before it (`-c`), so those installs
never disagree on a version. `staging.txt` is hand-written and installs
common.

Never edit a `.txt`. To add or bound a package, edit the `.in`, then:

    scripts/compile-requirements.sh        # keeps current pins, resolves the new package
    scripts/compile-requirements.sh -U     # moves everything to the latest the bounds allow

Commit the `.in` and `.txt` together. Python packages move only when the
`.txt` changes, so the Docker cache is right and `--no-cache` is never needed
for them. Dependabot (pip, `/requirements`) reads the generated files.
