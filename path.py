class Path:
    def __init__(self, path_id, prob):
        self.approximable_var = []
        self.non_approximable_var = []
        self.all_var = []
        self.input_approximations = []
        self.path_id = path_id
        self.path_prob = prob
