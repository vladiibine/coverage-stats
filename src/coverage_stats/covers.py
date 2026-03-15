from __future__ import annotations


class CoverageStatsError(Exception):
    pass


class CoverageStatsResolutionError(CoverageStatsError):
    pass


def covers(*refs):
    def decorator(fn):
        fn._covers_refs = refs
        return fn

    return decorator
