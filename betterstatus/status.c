#define _GNU_SOURCE // Required for execvpe
#include <errno.h>
#include <mqueue.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

int status;
int childpid;
int pipefds[2];

#define MAX_MSG_LEN 256
char status_msg[MAX_MSG_LEN];
char status_newmsg[MAX_MSG_LEN];
char status_mqfile[64];
mqd_t status_mqdes;

void child(char **argv) {
  // Setup env-vars to propagate to descendants
  char env0[64];
  snprintf(env0, 64, "STATUS_MQ=%s", status_mqfile);
  char *childenv[2] = {env0, NULL};

  // Redirect child's stdout to write end of pipe
  close(pipefds[0]);
  dup2(pipefds[1], fileno(stdout));

  execvpe(argv[2], argv+2, childenv);
}

void sigchld_handler(int code) {
  int status;
  int ret = waitpid(childpid, &status, WNOHANG);
  if (ret == -1) {
    fprintf(stderr, "waitpid() failed: %s\n", strerror(errno));
    exit(EXIT_FAILURE);
  }

  if (ret == childpid) {
    if (WIFEXITED(status) || WIFSIGNALED(status)) {
      fprintf(stderr, "child exited\n");
      exit(EXIT_SUCCESS);
    }
  }
}

void parent() {
  // Initialise message queue
  struct mq_attr attr;
  attr.mq_flags = O_NONBLOCK;
  attr.mq_maxmsg = 1;
  attr.mq_msgsize = MAX_MSG_LEN;
  status_mqdes = mq_open(status_mqfile, O_CREAT|O_RDONLY|O_NONBLOCK, 0600, &attr);
  if (status_mqdes == (mqd_t)-1) {
    fprintf(stderr, "mq_open() failed: %s\n", strerror(errno));
    exit(EXIT_FAILURE);
  }

  // Register child handler
  signal(SIGCHLD, sigchld_handler);

  // Redirect parent's stdin to read end of pipe
  close(pipefds[1]);
  dup2(pipefds[0], fileno(stdin));

  ssize_t n;
  char c;
  while (1) {
    if (mq_receive(status_mqdes, status_newmsg, MAX_MSG_LEN, NULL) == -1) {
      if (errno != EAGAIN) {
        fprintf(stderr, "mq_receive() failed: %s\n", strerror(errno));
        exit(EXIT_FAILURE);
      }
    }
    else
      strncpy(status_msg, status_newmsg, MAX_MSG_LEN);

    n = read(fileno(stdin), &c, 1);
    if (n == -1) {
      fprintf(stderr, "read() failed: %s\n", strerror(errno));
      exit(EXIT_FAILURE);
    }
    if (n == 0) {
      printf("\n\033[0K\033[F");
      fflush(stdout);
      exit(EXIT_SUCCESS);
    }

    write(fileno(stdout), &c, 1);
    // Intercept newlines in order to maintain the status bar
    if (c == '\n') {
      printf("\n%s\033[F\033[0K", status_msg);
      fflush(stdout);
    }
  }
}

int main(int argc, char **argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: status <message> <program> [ <args> ]\n");
    exit(EXIT_FAILURE);
  }

  strncpy(status_msg, argv[1], MAX_MSG_LEN);
  snprintf(status_mqfile, 64, "/status%ld", (long)getpid());

  status = pipe(pipefds);
  if (status == -1) {
    fprintf(stderr, "pipe() failed: %s\n", strerror(errno));
    exit(EXIT_FAILURE);
  }

  childpid = fork();
  if (childpid == -1) {
    fprintf(stderr, "fork() failed: %s\n", strerror(errno));
    exit(EXIT_FAILURE);
  }

  if (childpid == 0)
    parent();
  else
    child(argv);
}