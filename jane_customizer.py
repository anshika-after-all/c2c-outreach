"""PDF section 8.2 — custom resume hook for Jane Doe.

Copy this file when a client's layout does not use normal headings.
Register the new function in gmail_sender.HOOKS.
"""

from resume_customizer import customize_resume


def customize(job_description, source, destination, candidate_key):
    # Jane's file uses standard headings, so the shared engine can edit it.
    return customize_resume(job_description, source, destination, candidate_key)
