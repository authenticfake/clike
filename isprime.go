package main

import (
	"bufio"
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"
)

// IsPrime restituisce true se n è un numero primo.
// Algoritmo: gestisce i casi n < 2, pari, e poi testa i divisori dispari fino a sqrt(n).
func IsPrime(n int64) bool {
	if n < 2 {
		return false
	}
	if n%2 == 0 {
		return n == 2
	}
	limit := int64(math.Sqrt(float64(n)))
	for i := int64(3); i <= limit; i += 2 {
		if n%i == 0 {
			return false
		}
	}
	return true
}

func main() {
	reader := bufio.NewReader(os.Stdin)
	fmt.Print("Inserisci un numero: ")
	line, err := reader.ReadString('\n')
	if err != nil {
		fmt.Fprintln(os.Stderr, "Errore lettura:", err)
		os.Exit(1)
	}
	 s := strings.TrimSpace(line)
	n, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Numero non valido:", err)
		os.Exit(1)
	}
	if IsPrime(n) {
		fmt.Printf("%d è un numero primo\n", n)
	} else {
		fmt.Printf("%d non è un numero primo\n", n)
	}
}
