# approximability
Automated sensitivity analysis to determine path based approximability of program variables from the symbolic results produced by an [augmented Klee](https://github.com/ApproxSymate/klee).

To obtain program variables that can be approximated for a single path, run `python find_approx.py --single-path-approximation config.txt`

Note - Paths for output, source, and klee needs to be updated in the config.txt file before running the analysis. Examples can be found [here](https://github.com/ApproxSymate/evaluation/tree/master/benchmarks-with-approxsymate).

This project uses cinpy. See [here](https://github.com/csarn/cinpy) on how to set up cinpy. Also requires python3.

More information on how the sensitivity analaysis works can be found in the publication: 

H. De Silva, A. Santosa, N. Ho, W. Wong. 2019. ApproxSymate: Path Sensitive Program Approximation using Symbolic Execution. In Proceedings of the 20th ACM SIGPLAN/SIGBED Conference on Languages, Compilers, and Tools for Embedded Systems (LCTES ’19), June 23, 2019, Phoenix, AZ, USA.
