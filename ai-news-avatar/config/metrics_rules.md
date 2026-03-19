# Metrics Rules

## Purpose
These rules define how performance data changes creative decisions.

## Primary Metrics
- views
- engagedViews
- averageViewDuration
- averageViewPercentage
- estimatedMinutesWatched
- likes
- comments
- shares
- subscribersGained

## Decision Logic

### Case 1
High views, weak retention
- topic or title is strong
- opening may be good
- the body is losing attention

Action:
- shorten middle
- reduce setup
- increase information density

### Case 2
Low views, decent retention
- the video works for people who enter
- packaging is weak

Action:
- improve title
- improve first sentence
- improve first-frame clarity

### Case 3
Strong retention and strong views
- scale this topic pattern
- keep one or two elements constant
- test only one new improvement at a time

### Case 4
Weak views and weak retention
- bad topic fit or weak script

Action:
- drop the angle
- do not iterate tiny wording fixes on a dead concept

## Topic Buckets To Track
- model launches
- embedding / infra updates
- multimodal systems
- API launches
- consumer-facing product releases
- pricing / access changes

Each bucket should eventually show:
- total videos
- median views
- median retention
- win rate

## Improvement Discipline
Do not change:
- topic
- title style
- opening formula
- pacing
- render style

all at once.

Change 1-2 variables, then measure.
