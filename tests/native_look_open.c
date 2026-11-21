/* Host fixture: use the production file adapter and replace only the stock
 * fopen. Hidden visibility + section GC drop unrelated camera entry points. */
#include "../firmware/ep5_art_entry.c"

typedef void *(*open_callback)(const char *, const char *);
static open_callback backend;
void *ep5_file_open(const char *path, const char *mode)
{
    return backend(path, mode);
}

__attribute__((visibility("default")))
void *native_look_open(const char *path, open_callback open_file)
{
    backend = open_file;
    void *file = look_open(NULL, path);
    backend = NULL;
    return file;
}
