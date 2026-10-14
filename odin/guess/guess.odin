package guess

import "core:fmt"
import "core:math/rand"
import "core:os"
import "core:strconv"

main :: proc() {
  x: uint = rand.uint_max(100)
  buf: [8]byte
  // For reading the tails of very long lines that don't fit in buf.
  // This is not processed by the program.
  dummybuf: [256]byte
  prompt: string = "Guess a number 0-99: "
  s: string

  for {
    fmt.print(prompt)
    n, err := os.read(os.stdin, buf[:])
    if err != nil {
      return
    }

    if buf[n-1] != '\n' {
      fmt.println("Truncating input line:", string(buf[:]))
      for {
        nn, err := os.read(os.stdin, dummybuf[:])
        if err != nil {
          return
        }
        if dummybuf[nn-1] == '\n' {
          break
        }
      }
      s = string(buf[:])
    }
    else {
      s = string(buf[:n-1])
    }

    guess, ok := strconv.parse_uint(s)
    if !ok {
      prompt = "That was not a number! "
    } else if guess < x {
      prompt = "Go higher! "
    } else if guess > x {
      prompt = "Go lower! "
    } else {
      fmt.println("Bingo!")
      return
    }
  }
}