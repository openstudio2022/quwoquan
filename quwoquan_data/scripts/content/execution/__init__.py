"""Content execution package.

Public entry points import concrete owner modules explicitly.  The package import
must remain side-effect free so CLI help never loads retired orchestration.
"""
