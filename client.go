package main

import (
	"sync"
	"io/ioutil"
	"fmt"
	"net/http"
	"flag"
	"time"
)

func make_requests(count int, waitGroup *sync.WaitGroup) {
	for i := 0 ; i < count; i++ {
		response, err := http.Get("http://localhost:8888")
		if err != nil {
			fmt.Println("Got error message: " + err.Error())
		} else {
			_, err := ioutil.ReadAll(response.Body)
			if err != nil {
				fmt.Print("Unexpected error while reading body: " + err.Error())
			}
			response.Body.Close()
		}
	}
	waitGroup.Done()
}

func main() {
	threadCount := flag.Int("threads", 10, "Number of threads to run concurrently")
	requestCount := flag.Int("requests", 1, "Number of requests per thread")
	flag.Parse()
	fmt.Println("Using", *threadCount, "threads and", *requestCount, "requests per thread")
	var waitGroup sync.WaitGroup
	waitGroup.Add(*threadCount)

	start := time.Now()
	for i := 0; i < *threadCount; i++ {
		go make_requests(*requestCount, &waitGroup)
	}
	waitGroup.Wait()
	elapsed := time.Since(start)
	seconds := elapsed.Seconds()
	count := *threadCount * *requestCount
	fmt.Println("Did ", count, "requests in ", seconds, "seconds")
	perSeconds := 0.0
	if seconds > 0 {
		perSeconds = float64(count) / seconds
	}
	fmt.Println("Rate:", perSeconds, "requests / second")
}