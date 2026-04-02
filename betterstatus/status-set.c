#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <mqueue.h>

#define MAX_MSG_LEN 256
char status_newmsg[MAX_MSG_LEN];
char *status_mqfile;
mqd_t status_mqdes;

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: status-set <message>\n");
    exit(EXIT_FAILURE);
  }

  status_mqfile = getenv("STATUS_MQ");
  if (!status_mqfile) {
    fprintf(stderr, "no status message queue found\n");
    exit(EXIT_FAILURE);
  }

  status_mqdes = mq_open(status_mqfile, O_WRONLY|O_NONBLOCK);
  if (status_mqdes == (mqd_t)-1) {
    fprintf(stderr, "mq_open() failed: %s\n", strerror(errno));
    exit(EXIT_FAILURE);
  }

  strncpy(status_newmsg, argv[1], MAX_MSG_LEN);
  if (mq_send(status_mqdes, status_newmsg, MAX_MSG_LEN, 0) == -1) {
    fprintf(stderr, "mq_send() failed: %s\n", strerror(errno));
    exit(EXIT_FAILURE);
  }
}