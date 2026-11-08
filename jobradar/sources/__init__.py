"""Job source adapters. Each exposes NAME and fetch(cfg) -> list[Job]."""
from . import (remotive, remoteok, himalayas, arbeitnow, jobicy, workingnomads,
               weworkremotely, ats)

REGISTRY = {
    remotive.NAME: remotive.fetch,
    remoteok.NAME: remoteok.fetch,
    himalayas.NAME: himalayas.fetch,
    arbeitnow.NAME: arbeitnow.fetch,
    jobicy.NAME: jobicy.fetch,
    workingnomads.NAME: workingnomads.fetch,
    weworkremotely.NAME: weworkremotely.fetch,
    "greenhouse": ats.fetch_greenhouse,
    "lever": ats.fetch_lever,
    "ashby": ats.fetch_ashby,
    "recruitee": ats.fetch_recruitee,
}
