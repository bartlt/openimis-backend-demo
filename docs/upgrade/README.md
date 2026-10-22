# Django 5.2 / Graphene 3 upgrade: GraphQL API compatibility evidence

| File | What it is |
|------|------------|
| `schema-before.graphql` | Schema on `main` (Django 4.2, Graphene 2), tag `baseline-django42-green` |
| `schema-after.graphql` | Schema after the upgrade (Django 5.2, Graphene 3) |
| `schema-diff-normalized.diff` | Diff of the two schemas with descriptions stripped and types/fields sorted |

Both files were produced with:

```bash
cd openIMIS
python manage.py graphql_schema --schema openIMIS.schema.schema --out ../docs/upgrade/schema-<before|after>.graphql
```

## Result

`graphql.find_breaking_changes` / `find_dangerous_changes` (graphql-core 3.2) between the two
schemas: **0 breaking, 0 dangerous**. Every type, field, argument and enum value
that existed before still exists, with the same name and type.

The raw text diff is large because Graphene 3 prints more documentation (descriptions on
relay `Connection`/`Edge`/`PageInfo` fields, the `mutationExtensions` input and others),
which has no effect on clients. With descriptions removed, the only differences are:

1. **Decimal input defaults print as `"0"` instead of `0`** (9 Decimal fields on the product
   mutation input types, 21 occurrences in total, e.g. `lumpSum`, `premiumAdult`, `limitAdult`). Graphene 3's `Decimal`
   scalar serializes to a string, so the default value is printed as a string. The default is
   still zero, and clients that omit the field get the same value as before.
2. **`DjangoDebug.exceptions` / `DjangoDebugException`** were added by graphene-django 3's
   debug middleware (the `_debug` field, used only in development). Additive.

Enum type names are kept identical with `GRAPHENE["DJANGO_CHOICE_FIELD_ENUM_V2_NAMING"] = True`;
without it graphene-django 3 renames ~250 choice enums (e.g. `InsureeStatus` →
`InsureeInsureeStatusChoices`), which would break the frontend's queries.

To reproduce the normalized diff:

```python
from graphql import build_schema, print_schema, lexicographic_sort_schema
from graphql.language import parse, print_ast, visit, Visitor

class StripDescriptions(Visitor):
    def enter(self, node, *args):
        if getattr(node, "description", None) is not None:
            node.description = None

def normalize(path):
    doc = parse(open(path).read())
    visit(doc, StripDescriptions())
    return print_schema(lexicographic_sort_schema(build_schema(print_ast(doc))))
```
