//go:build !js

package main

import (
	"encoding/json"
	"fmt"
	"os"
)

func main() {
	b, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	out := verifyEvidence(string(b), os.Args[2], os.Args[3])
	j, _ := json.Marshal(out)
	fmt.Println(string(j))
	if !out.Verified {
		os.Exit(1)
	}
}
