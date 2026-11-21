#ifndef EP5_LOOK_PATH_H
#define EP5_LOOK_PATH_H

#define EP5_LOOK_ROOT "EP5LUT/"

static inline const char *ep5_look_after_root(const char *path)
{
    if (!path) return 0;
    for (const char *prefix = EP5_LOOK_ROOT; *prefix; ++prefix, ++path)
        if (*path != *prefix) return 0;
    return path;
}

static inline int ep5_look_name_equal(const char *a, const char *b)
{
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

/* The card format uses 8.3 names and permits table numbers 1 through 16. */
static inline int ep5_look_valid_leaf(const char *name)
{
    if (ep5_look_name_equal(name, "INDEX.EP5") || ep5_look_name_equal(name, "FX.EP5"))
        return 1;
    if (*name++ != 'L') return 0;
    for (unsigned i = 0; i < 5; ++i)
        if (*name++ != '0') return 0;
    if (!((name[0] == '0' && name[1] >= '1' && name[1] <= '9') ||
          (name[0] == '1' && name[1] >= '0' && name[1] <= '6')))
        return 0;
    return ep5_look_name_equal(name + 2, ".LUT");
}

#endif
