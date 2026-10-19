# Feature: Company knowledge

## Purpose
Store company facts, policies, and extracted document text so AI Employees and staff can use them in chat and tasks. **Files are not retained** after extract.

## Who
| Role | Read | Write / extract |
|------|------|-----------------|
| Owner | Yes | Yes |
| AI Administrator | Yes | Yes |
| Contract Manager | Yes | Yes |
| Manager | Yes | Yes |
| Reservation / Member | Yes | No |
| Accounting | Yes | No |

## Frontend
- Nav **Knowledge** (`knowledge.read`)
- List + filter (extract / manual / category)
- **Upload document → extract** (hidden without `knowledge.write`)
- **Add note manually**
- **Search**

## Backend
- `GET /companies/{id}/knowledge`
- `POST /companies/{id}/knowledge` — manual note
- `POST /companies/{id}/knowledge/ingest-extract` — multipart file + title + category
- `POST /companies/{id}/knowledge/search`

## Flow after hire
1. Hire AI Employee  
2. Extract contracts / SOPs into knowledge  
3. Staff chat or tasks use knowledge under policy  
