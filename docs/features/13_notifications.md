# Feature: Notifications

## Purpose
In-app alerts for approvals, task outcomes, and company events. Complements **Inbox** (work queue) with a read/unread feed.

## Who
Any authenticated company user (scoped to their company).

## Frontend
- Nav **Notifications** and top-bar bell
- Filter all / unread
- Mark one or all as read
- **Open** jumps to task / approvals / results when linked

## Backend
- `GET /companies/{id}/notifications`
- `POST /companies/{id}/notifications/{id}/read`
- `POST /companies/{id}/notifications/read-all`
