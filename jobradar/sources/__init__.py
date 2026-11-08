"""Job source adapters. Each exposes NAME and fetch(cfg) -> list[Job]."""
from . import (remotive, remoteok, himalayas, arbeitnow, jobicy, workingnomads,
               weworkremotely, ats, karriere_at, carierista, workable,
               linkedin_alerts)

REGISTRY = {
    remotive.NAME: remotive.fetch,
    remoteok.NAME: remoteok.fetch,
    himalayas.NAME: himalayas.fetch,
    arbeitnow.NAME: arbeitnow.fetch,
    jobicy.NAME: jobicy.fetch,
    workingnomads.NAME: workingnomads.fetch,
    weworkremotely.NAME: weworkremotely.fetch,
    karriere_at.NAME: karriere_at.fetch,
    carierista.NAME: carierista.fetch,
    workable.NAME: workable.fetch,
    linkedin_alerts.NAME: linkedin_alerts.fetch,
    "greenhouse": ats.fetch_greenhouse,
    "lever": ats.fetch_lever,
    "ashby": ats.fetch_ashby,
    "recruitee": ats.fetch_recruitee,
}
