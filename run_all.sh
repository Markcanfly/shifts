
for filename in schedule_data/*.json; do
    echo Running $filename
    $SOLVER_PYTHONPATH main.py $filename GRB 1 0 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 1 1 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 1 100 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 1 1000 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 1 10000 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 100 1 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 0 1 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 10000 1 >> log.txt &
    $SOLVER_PYTHONPATH main.py $filename GRB 1000 1 >> log.txt &
    wait
    mv $filename done/$filename
done
