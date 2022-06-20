from django.db.models import CharField, Lookup


class Empty(Lookup):
    """
    Filter on whether a string is empty.
    """
    lookup_name = 'empty'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return f'CAST(LENGTH({lhs}) AS BOOLEAN) != {rhs}', params


CharField.register_lookup(Empty)
