//go:build js && wasm

package main

import (
	"encoding/json"
	"syscall/js"
)

func main() {
	js.Global().Set("verifySnpEvidence", js.FuncOf(func(this js.Value, args []js.Value) any {
		if len(args) != 3 {
			return `{"verified":false,"error":"missing verifier input"}`
		}
		out, _ := json.Marshal(verifyEvidence(args[0].String(), args[1].String(), args[2].String()))
		return string(out)
	}))
	select {}
}
