def calibrate_fine_increment():
    
    """determine the step size of a fine DAC increment in
    log2 units at various coarse DAC points"""
    
    def multi_sample(cnt=10):
        
        """take cnt measurements of the frequency and return the
        result in log2 units"""
        
        running = 0
        
        for q in range(cnt):
            time.sleep(0.1)
            f = sample_to_frequency(get_sample_reject_anomalies())
            running += log2(f)
        return running/cnt  # average the measurements
    
    results = []
    
    
    get_sample_reject_anomalies()  # discard old measurements
    for cors in range(0,255,16):
        
        send_dac_value(1, 0)
        # steps of 16 so divide by 16 to get relevant index when looking up
        send_dac_value(0, cors)
        c1 = multi_sample(5)
        send_dac_value(0, cors+1)
        c2 = multi_sample(5)
        send_dac_value(1, 255)  # max out fine measurement and use
        # the difference to work out the range it covers
        f = multi_sample(5)

        fine_range = f - c2  # how many log2 units is the whole 255 range worth?
        coarse_range = c2 - c1
        fine_increment = fine_range/255.0
        fine_as_frac_of_coarse = fine_increment / coarse_range
        results.append(fine_as_frac_of_coarse)
        print(cors, fine_as_frac_of_coarse)
        
    return results