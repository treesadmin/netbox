from django.db.models import IntegerField, Lookup, Transform, lookups


class NetFieldDecoratorMixin(object):

    def process_lhs(self, qn, connection, lhs=None):
        lhs = lhs or self.lhs
        lhs_string, lhs_params = qn.compile(lhs)
        lhs_string = f'TEXT({lhs_string})'
        return lhs_string, lhs_params


class IExact(NetFieldDecoratorMixin, lookups.IExact):

    def get_rhs_op(self, connection, rhs):
        return f'= LOWER({rhs})'


class EndsWith(NetFieldDecoratorMixin, lookups.EndsWith):
    pass


class IEndsWith(NetFieldDecoratorMixin, lookups.IEndsWith):
    pass

    def get_rhs_op(self, connection, rhs):
        return f'LIKE LOWER({rhs})'


class StartsWith(NetFieldDecoratorMixin, lookups.StartsWith):
    lookup_name = 'startswith'


class IStartsWith(NetFieldDecoratorMixin, lookups.IStartsWith):
    pass

    def get_rhs_op(self, connection, rhs):
        return f'LIKE LOWER({rhs})'


class Regex(NetFieldDecoratorMixin, lookups.Regex):
    pass


class IRegex(NetFieldDecoratorMixin, lookups.IRegex):
    pass


class NetContainsOrEquals(Lookup):
    lookup_name = 'net_contains_or_equals'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return f'{lhs} >>= {rhs}', params


class NetContains(Lookup):
    lookup_name = 'net_contains'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return f'{lhs} >> {rhs}', params


class NetContained(Lookup):
    lookup_name = 'net_contained'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return f'{lhs} << {rhs}', params


class NetContainedOrEqual(Lookup):
    lookup_name = 'net_contained_or_equal'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return f'{lhs} <<= {rhs}', params


class NetHost(Lookup):
    lookup_name = 'net_host'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        # Query parameters are automatically converted to IPNetwork objects, which are then turned to strings. We need
        # to omit the mask portion of the object's string representation to match PostgreSQL's HOST() function.
        if rhs_params:
            rhs_params[0] = rhs_params[0].split('/')[0]
        params = lhs_params + rhs_params
        return f'HOST({lhs}) = {rhs}', params


class NetIn(Lookup):
    lookup_name = 'net_in'

    def get_prep_lookup(self):
        # Don't cast the query value to a netaddr object, since it may or may not include a mask.
        return self.rhs

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        with_mask, without_mask = [], []
        for address in rhs_params[0]:
            if '/' in address:
                with_mask.append(address)
            else:
                without_mask.append(address)

        address_in_clause = self.create_in_clause(f'{lhs} IN (', len(with_mask))
        host_in_clause = self.create_in_clause(f'HOST({lhs}) IN (', len(without_mask))

        if with_mask and not without_mask:
            return address_in_clause, with_mask
        elif not with_mask and without_mask:
            return host_in_clause, without_mask

        in_clause = f'({address_in_clause}) OR ({host_in_clause})'
        with_mask.extend(without_mask)
        return in_clause, with_mask

    @staticmethod
    def create_in_clause(clause_part, max_size):
        clause_elements = [clause_part]
        for offset in range(max_size):
            if offset > 0:
                clause_elements.append(', ')
            clause_elements.append('%s')
        clause_elements.append(')')
        return ''.join(clause_elements)


class NetHostContained(Lookup):
    """
    Check for the host portion of an IP address without regard to its mask. This allows us to find e.g. 192.0.2.1/24
    when specifying a parent prefix of 192.0.2.0/26.
    """
    lookup_name = 'net_host_contained'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return f'CAST(HOST({lhs}) AS INET) <<= {rhs}', params


class NetFamily(Transform):
    lookup_name = 'family'
    function = 'FAMILY'

    @property
    def output_field(self):
        return IntegerField()


class NetMaskLength(Transform):
    function = 'MASKLEN'
    lookup_name = 'net_mask_length'

    @property
    def output_field(self):
        return IntegerField()


class Host(Transform):
    function = 'HOST'
    lookup_name = 'host'


class Inet(Transform):
    function = 'INET'
    lookup_name = 'inet'
