# Feature: Users, invitations & job positions

## Who can invite
| Actor | Can invite | Can assign `ai_admin` | Can change Owner |
|-------|------------|----------------------|------------------|
| Owner | Yes | Yes | No |
| AI Administrator (`ai_admin`) | Yes (operational roles) | No | No |
| Administration | Yes (operational roles) | No | No |
| Other roles | No | No | No |

## Navigation
Menus without the required permission are **hidden** (not merely disabled).
- `users` requires `team.manage` (owner, ai_admin, administration)
- Operational roles see Chat / Tasks / Knowledge as allowed by their matrix

## Backend
- `POST /invitations` — owner or `team.manage`
- `PUT /users/{id}/role` — owner or `team.manage` (ai_admin assign = owner only)
- `PUT /administrators/{id}` — owner only
