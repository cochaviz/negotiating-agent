import json
import sys

def run(number_of_runs=10) -> list[dict]:
    all_results = []

    for _ in range(number_of_runs):
        exec(open("run.py").read())

        with open("results/results_summary.json", "r") as f:
            results = json.loads(f.read())
            all_results.append(results)

    return all_results

def average_social_welfare(results: list[dict]) -> float:
    social_welfare = list(map((lambda m: float(m["social_welfare"])), results))
    return sum(social_welfare)/len(social_welfare)


if __name__=="__main__":
    try:
        results = run(int(sys.argv[1]))
    except:
        results = run()

    print(average_social_welfare(results))
