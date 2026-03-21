/*
 * LD_PRELOAD shim: intercept bind() and force IPv4 sockets to bind
 * to INADDR_ANY (0.0.0.0) instead of a specific IP.
 *
 * This allows the Livox SDK to advertise the real host IP to the LiDAR
 * (so it knows where to send data) while binding inside a Docker container
 * where that IP doesn't exist on any interface.
 *
 * Compile: gcc -shared -fPIC -o /usr/lib/bind_any.so bind_any.c -ldl
 * Usage:   LD_PRELOAD=/usr/lib/bind_any.so ros2 launch ...
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <string.h>

typedef int (*bind_func_t)(int, const struct sockaddr *, socklen_t);

int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    bind_func_t original_bind = (bind_func_t)dlsym(RTLD_NEXT, "bind");

    if (addr && addr->sa_family == AF_INET && addrlen >= sizeof(struct sockaddr_in)) {
        struct sockaddr_in modified;
        memcpy(&modified, addr, sizeof(modified));
        modified.sin_addr.s_addr = htonl(INADDR_ANY);
        return original_bind(sockfd, (struct sockaddr *)&modified, addrlen);
    }

    return original_bind(sockfd, addr, addrlen);
}
