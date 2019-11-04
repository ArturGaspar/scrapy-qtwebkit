def get_js_value(jsvalue):
    if jsvalue.is_object():
        r = {}
        for prop in (jsvalue.object_enumerate_properties() or []):
            r[prop] = get_js_value(jsvalue.object_get_property(prop))
        return r
    elif jsvalue.is_boolean():
        return jsvalue.to_boolean()
    elif jsvalue.is_number():
        return jsvalue.to_double()
    elif jsvalue.is_string():
        # Data seems to be UTF-8. TODO: investigate and add test for this.
        return jsvalue.to_string_as_bytes().get_data().decode('utf-8')
    elif jsvalue.is_null() or jsvalue.is_undefined():
        return None
    else:
        return jsvalue.to_string_as_bytes().get_data().decode('utf-8')
